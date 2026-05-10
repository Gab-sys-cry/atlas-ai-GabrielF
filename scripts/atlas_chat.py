"""
scripts/atlas_chat.py -- Point d'entrée CLI pour Atlas.

Commandes :
    python scripts/atlas_chat.py                          # config/atlas.yml par défaut
    python scripts/atlas_chat.py --config config/default.yml
    python scripts/atlas_chat.py --model qwen3:8b         # surcharge CLI
    python scripts/atlas_chat.py --no-stream
    python scripts/atlas_chat.py --list-models
    python scripts/atlas_chat.py --show-metrics
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from atlas.config import AtlasConfig
from atlas.llm import OllamaClient, OllamaError
from atlas.memory import ConversationMemory, LongTermMemory
from atlas.monitoring import SessionMetrics, Timer, TurnMetrics, TraceLogger, setup_logger
from atlas.guardrails import InputGuardrails, OutputGuardrails, GuardrailError, TopicBlocked

# Argument parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atlas-chat",
        description="Atlas -- Client CLI multi-tours pour Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  atlas-chat                                  # profil atlas.yml
  atlas-chat --config config/default.yml      # profil dev
  atlas-chat --model qwen3:8b --show-metrics
  atlas-chat --list-models
        """,
    )
    p.add_argument("--model", "-m", default=None, help="Surcharge le modèle du YAML")
    p.add_argument("--timeout", "-t", type=float, default=None, help="Timeout HTTP (s)")
    p.add_argument("--no-stream", action="store_true", help="Désactiver le streaming")
    p.add_argument("--list-models", action="store_true", help="Lister les modèles et quitter")
    p.add_argument("--show-metrics", action="store_true", help="Métriques après chaque réponse")
    p.add_argument("--config", default=None, help="Chemin vers un fichier YAML (défaut : config/atlas.yml)")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    p.add_argument("--version", action="version", version="Atlas 0.4.0")
    return p


def apply_cli_overrides(cfg: dict, args: argparse.Namespace) -> dict:
    """Les flags CLI ont priorité absolue sur le YAML."""
    if args.model:        cfg["model"]        = args.model
    if args.timeout:      cfg["timeout"]      = args.timeout
    if args.no_stream:    cfg["stream"]       = False
    if args.show_metrics: cfg["show_metrics"] = True
    if args.log_level:    cfg["log_level"]    = args.log_level
    return cfg



# Helpers


BANNER = r"""
      _     _________  _____          _       ______
     / \   |  _   _  ||_   _|        / \    .' ____ \
    / _ \  |_/ | | \_|  | |         / _ \   | (___ \_|
   / ___ \     | |      | |   _    / ___ \   _.____`.
 _/ /   \ \_  _| |_    _| |__/ | _/ /   \ \_| \____) |
|____| |____||_____|  |________||____| |____|\______.'

  Assistant IA local · Ollama
"""

HELP_TEXT = """
Commandes disponibles :
  /quit  ou  /exit         -- quitter
  /clear                   -- effacer l'historique de session
  /history                 -- afficher l'historique + estimation tokens
  /model                   -- afficher le modèle actif
  /metrics                 -- afficher les métriques de session
  /memory                  -- afficher les souvenirs long terme stockés
  /forget <query>          -- supprimer les souvenirs liés à <query>
  /config                  -- afficher la configuration active
  /help                    -- afficher cette aide
"""


def print_separator(char="─", width=60):
    print(char * width)


def print_metrics(metrics: SessionMetrics) -> None:
    print_separator()
    print("Métriques de session :")
    print(metrics.summary())
    print_separator()



# Boucle principale


def run_interactive(cfg: dict) -> None:
    setup_logger("atlas", cfg["log_level"])

    client = OllamaClient(
        base_url=cfg["base_url"],
        model=cfg["model"],
        timeout=cfg["timeout"],
    )

    memory = ConversationMemory(
        system_prompt=cfg["system_prompt"],
        max_turns=cfg["max_turns"],
    )

    long_term: LongTermMemory | None = None
    if cfg["long_term_enabled"]:
        long_term = LongTermMemory(
            db_path=_ROOT / cfg["db_path"],
            collection_name=cfg["collection"],
            top_k=cfg["top_k"],
            min_similarity=cfg["min_similarity"],
        )

    tracer: TraceLogger | None = None
    if cfg["tracing_enabled"]:
        tracer = TraceLogger(_ROOT / cfg["trace_log_path"])

    session = SessionMetrics()

    g_enabled = cfg["guardrails_enabled"]
    input_guard = InputGuardrails(
        max_length=cfg["max_input_length"],
        blocked_patterns=cfg["blocked_patterns"]    if g_enabled else [],
        blocked_topics=cfg["blocked_topics"]        if g_enabled else [],
        persona_name=cfg["persona_name"],
        pii_detection=cfg["pii_detection"]          if g_enabled else False,
        prompt_injection=cfg["prompt_injection"]    if g_enabled else False,
        rate_limit_enabled=cfg["rate_limit_enabled"] if g_enabled else False,
        rate_limit_max=cfg["rate_limit_max"],
        rate_limit_window_s=cfg["rate_limit_window_s"],
    )
    output_guard = OutputGuardrails(
        pii_detection=cfg["pii_detection"] if g_enabled else False,
    )

    ollama_options = {
        "temperature": cfg["temperature"],
        "top_p":       cfg["top_p"],
        "num_ctx":     cfg["num_ctx"],
    }

    if not client.health_check():
        print(f"Impossible de joindre Ollama sur {cfg['base_url']}.")
        print("Démarrez le serveur : `ollama serve`")
        sys.exit(1)

    print(BANNER)
    mem_status = f"longue activée ({long_term.count} souvenirs)" if long_term else "session uniquement"
    print(f"  Modèle   : {cfg['model']}  (temp={cfg['temperature']}, top_p={cfg['top_p']})")
    print(f"  Mémoire  : {mem_status}")
    print(f"  Traces   : {cfg['trace_log_path'] if tracer else 'désactivées'}")
    print()
    print("  Tapez /help pour la liste des commandes.")
    print_separator()

    turn = 0

    while True:
        try:
            user_input = input("\nVous : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAu revoir !")
            if cfg["show_metrics"]:
                print_metrics(session)
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # --- Commandes internes ---

        if cmd in ("/quit", "/exit"):
            print("\nAu revoir !")
            if cfg["show_metrics"]:
                print_metrics(session)
            break

        elif cmd == "/clear":
            memory.clear()
            print("Historique de session effacé.")
            continue

        elif cmd == "/history":
            print("\nHistorique :")
            print(memory.summary())
            continue

        elif cmd == "/model":
            print(f"Modèle actif : {cfg['model']}")
            continue

        elif cmd == "/metrics":
            print_metrics(session)
            continue

        elif cmd == "/config":
            print("\nConfiguration active :")
            for k, v in cfg.items():
                if k != "system_prompt":
                    print(f"  {k:<25} : {v}")
            print(f"  {'system_prompt':<25} : {cfg['system_prompt'][:60].strip()}…")
            continue

        elif cmd == "/memory":
            if not long_term:
                print("Mémoire longue désactivée.")
            else:
                n = long_term.count
                print(f"\nMémoire longue -- {n} souvenir(s) stocké(s).")
                if n > 0:
                    print_separator("·")
                    import datetime
                    items = long_term._col.get(limit=10, include=["documents", "metadatas"])
                    for idx, (doc, meta) in enumerate(zip(items["documents"], items["metadatas"]), 1):
                        ts = datetime.datetime.fromtimestamp(meta.get("timestamp", 0)).strftime("%d/%m %H:%M")
                        preview = doc[:100] + ("..." if len(doc) > 100 else "")
                        print(f"  [{idx}] {ts} -- {preview}")
            continue

        elif cmd.startswith("/forget "):
            query = user_input[8:].strip()
            if not long_term:
                print("Mémoire longue désactivée.")
            elif not query:
                print("Usage : /forget <sujet>")
            else:
                n = long_term.forget(query)
                print(f"{n} souvenir(s) supprimé(s) pour : « {query} »")
            continue

        elif cmd == "/help":
            print(HELP_TEXT)
            continue

        # --- Guardrails entrée ---

        guardrails_triggered: list[str] = []
        try:
            user_input, guardrails_triggered = input_guard.validate(user_input)
        except TopicBlocked as e:
            print(f"\n{cfg['persona_name']} :")
            print("·" * 60)
            print(e.polite_reply)
            if tracer:
                tracer.write(model=cfg["model"], user_message=user_input,
                    assistant_message=e.polite_reply, latency_ms=0,
                    guardrails_triggered=["topic_blocked"])
            continue
        except GuardrailError as e:
            print(f"Bloqué : {e}")
            continue

        if guardrails_triggered:
            print(f"  [PII masquée(s) : {', '.join(guardrails_triggered)}]")

        # --- Injection mémoire longue ---

        memory_hits = 0
        if long_term:
            memory_block = long_term.build_memory_block(user_input)
            if memory_block:
                enriched = cfg["system_prompt"].rstrip() + "\n\n" + memory_block
                memory.update_system_prompt(enriched)
                memory_hits = len(memory_block.split("\n")) - 2

        memory.add_user(user_input)
        turn += 1

        print(f"\n{cfg['persona_name']} ({cfg['model']}) :")
        print_separator("·")

        try:
            with Timer() as t:
                result = client.chat(
                    memory.get_messages(),
                    stream=cfg["stream"],
                    options=ollama_options,
                )
                if not cfg["stream"]:
                    print(result["response"])

        except OllamaError as e:
            print(f"\nErreur : {e}")
            memory._history.pop()
            continue

        # --- Guardrails sortie ---

        response, out_triggered = output_guard.process(result["response"])
        guardrails_triggered.extend(out_triggered)

        memory.add_assistant(response)

        if long_term:
            long_term.store(user_msg=user_input, assistant_msg=response)

        # --- Trace JSONL ---

        if tracer:
            tracer.write(
                model=cfg["model"],
                user_message=user_input,
                assistant_message=response,
                latency_ms=t.elapsed_s * 1000,
                prompt_tokens=result["prompt_tokens"],
                completion_tokens=result["completion_tokens"],
                memory_hits=memory_hits,
                guardrails_triggered=guardrails_triggered,
            )

        metrics = TurnMetrics(
            turn_index=turn,
            input_chars=len(user_input),
            output_chars=len(response),
            latency_s=t.elapsed_s,
            model=cfg["model"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
        )
        session.record(metrics)

        if cfg["show_metrics"]:
            print_separator("·")
            print(
                f"  {t.elapsed_s:.2f}s | "
                f"pt={result['prompt_tokens']} ct={result['completion_tokens']} | "
                f"~{memory.estimate_tokens()} tokens contexte"
            )



# list-models


def cmd_list_models(cfg: dict) -> None:
    client = OllamaClient(base_url=cfg["base_url"], model=cfg["model"], timeout=10.0)
    try:
        models = client.list_models()
    except OllamaError as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    if not models:
        print("Aucun modèle trouvé.")
        return
    print(f"\n{'Nom':<35} {'Taille':>12}  Famille")
    print_separator()
    for m in models:
        size_gb = m.get("size", 0) / 1e9
        family  = m.get("details", {}).get("family", "--")
        print(f"  {m['name']:<33} {size_gb:>8.2f} GB  {family}")
    print()


# Main

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Priorité : --config CLI > config/atlas.yml > config/default.yml (fallback)
    config_path = args.config or _ROOT / "config" / "atlas.yml"
    if not Path(config_path).exists():
        config_path = _ROOT / "config" / "default.yml"

    atlas_cfg = AtlasConfig.from_yaml(config_path)
    cfg = atlas_cfg.to_flat_dict()
    cfg = apply_cli_overrides(cfg, args)

    if args.list_models:
        cmd_list_models(cfg)
        return

    run_interactive(cfg)


if __name__ == "__main__":
    main()