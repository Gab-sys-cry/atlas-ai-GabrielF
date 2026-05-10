#!/usr/bin/env python3
"""
scripts/atlas_chat.py -- Point d'entrée CLI pour Atlas.

Commandes :
-----
    python scripts/atlas_chat.py                     # session interactive
    python scripts/atlas_chat.py --model llama3:8b   # modèle custom
    python scripts/atlas_chat.py --no-stream          # sans streaming
    python scripts/atlas_chat.py --list-models        # lister les modèles
    python scripts/atlas_chat.py --timeout 60         # timeout custom
    python scripts/atlas_chat.py --show-metrics       # afficher les métriques
    python scripts/atlas_chat.py --config config/default.yml

"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml

from atlas.llm import OllamaClient, OllamaError
from atlas.memory import ConversationMemory, LongTermMemory
from atlas.monitoring import SessionMetrics, Timer, TurnMetrics, setup_logger
from atlas.guardrails import InputGuardrails, OutputGuardrails, GuardrailError, TopicBlocked



# Chargement de la configuration YAML


def load_config(path: str | None) -> dict:
    """
    Charge et retourne la config YAML.
    """
    target = Path(path) if path else _ROOT / "config" / "default.yml"
    if not target.exists():
        sys.exit(f"Erreur : fichier de configuration introuvable : {target}")
    with open(target, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg:
        sys.exit(f"Erreur : fichier de configuration vide : {target}")
    return cfg


def merge_config(config: dict, args: argparse.Namespace) -> dict:
    """
    Lit la config YAML sans valeurs par défaut codées en dur.
    Seules les surcharges CLI sont appliquées par-dessus.
    """
    def require(section: str, key: str):
        value = config.get(section, {}).get(key)
        if value is None:
            sys.exit(f"Erreur : clé manquante dans le YAML -- [{section}] {key}")
        return value

    cfg = {
        # serveur
        "base_url":    require("server", "base_url"),
        "timeout":     require("server", "timeout"),
        "stream":      require("server", "stream"),
        # modèle
        "model":       require("model", "name"),
        "temperature": require("model", "temperature"),
        "top_p":       require("model", "top_p"),
        "num_ctx":     require("model", "num_ctx"),
        # persona
        "persona_name":  require("persona", "name"),
        "system_prompt": require("persona", "system_prompt"),
        # mémoire courte
        "max_turns": require("memory", "max_turns"),
        # mémoire longue
        "long_term_enabled": require("memory", "long_term_enabled"),
        "db_path":           require("memory", "db_path"),
        "collection":        require("memory", "collection"),
        "top_k":             require("memory", "top_k"),
        "min_similarity":    require("memory", "min_similarity"),
        # guardrails
        "guardrails_enabled": require("guardrails", "enabled"),
        "max_input_length":   require("guardrails", "max_input_length"),
        "blocked_topics":     config.get("guardrails", {}).get("blocked_topics", []),
        "blocked_patterns":   config.get("guardrails", {}).get("blocked_patterns", []),
        # ui
        "log_level":    require("ui", "log_level"),
        "show_metrics": require("ui", "show_metrics"),
    }

    # Surcharges CLI (priorité absolue)
    if args.model:
        cfg["model"] = args.model
    if args.timeout is not None:
        cfg["timeout"] = args.timeout
    if args.no_stream:
        cfg["stream"] = False
    if args.show_metrics:
        cfg["show_metrics"] = True
    if args.log_level:
        cfg["log_level"] = args.log_level

    return cfg



# Argument parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atlas-chat",
        description="Atlas -- Client CLI multi-tours pour Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  atlas-chat                              # session interactive (défaut)
  atlas-chat --model llama3:8b            # choisir un autre modèle
  atlas-chat --no-stream --show-metrics   # sans streaming + stats
  atlas-chat --list-models                # lister les modèles disponibles
  atlas-chat --config config/default.yml  # config custom
        """,
    )
    p.add_argument("--model", "-m", default=None, help="Modèle Ollama à utiliser")
    p.add_argument("--timeout", "-t", type=float, default=None, help="Timeout HTTP en secondes")
    p.add_argument("--no-stream", action="store_true", help="Désactiver le streaming")
    p.add_argument("--list-models", action="store_true", help="Lister les modèles disponibles et quitter")
    p.add_argument("--show-metrics", action="store_true", help="Afficher les métriques après chaque réponse")
    p.add_argument("--config", default=None, help="Chemin vers un fichier de config YAML")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=None)
    p.add_argument("--version", action="version", version="Atlas 0.2.0")
    return p


# Affichage

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
  /help                    -- afficher cette aide
"""


def print_separator(char: str = "─", width: int = 60) -> None:
    print(char * width)


def print_metrics(metrics: SessionMetrics) -> None:
    print_separator()
    print("📊 Métriques de session :")
    print(metrics.summary())
    print_separator()


# Boucle interactive principale


def run_interactive(cfg: dict) -> None:
    """Boucle REPL principale."""

    setup_logger("atlas", cfg["log_level"])

    client = OllamaClient(
        base_url=cfg["base_url"],
        model=cfg["model"],
        timeout=cfg["timeout"],
    )

    # Mémoire courte -- session en cours
    memory = ConversationMemory(
        system_prompt=cfg["system_prompt"],
        max_turns=cfg["max_turns"],
    )

    # Mémoire longue -- inter-sessions (ChromaDB)
    long_term: LongTermMemory | None = None
    if cfg["long_term_enabled"]:
        db_path = _ROOT / cfg["db_path"]
        long_term = LongTermMemory(
            db_path=db_path,
            collection_name=cfg["collection"],
            top_k=cfg["top_k"],
            min_similarity=cfg["min_similarity"],
        )

    session = SessionMetrics()

    input_guard = InputGuardrails(
        max_length=cfg["max_input_length"],
        blocked_patterns=cfg["blocked_patterns"] if cfg["guardrails_enabled"] else [],
        blocked_topics=cfg["blocked_topics"] if cfg["guardrails_enabled"] else [],
        persona_name=cfg["persona_name"],
    )
    output_guard = OutputGuardrails()

    ollama_options = {
        "temperature": cfg["temperature"],
        "top_p":       cfg["top_p"],
        "num_ctx":     cfg["num_ctx"],
    }

    # Vérification santé
    if not client.health_check():
        print(f"Impossible de joindre Ollama sur {cfg['base_url']}.")
        print("   Démarrez le serveur : `ollama serve`")
        sys.exit(1)

    # Bannière
    print(BANNER)
    print(f"  Modèle   : {cfg['model']}  (temp={cfg['temperature']}, top_p={cfg['top_p']}, ctx={cfg['num_ctx']})")
    print(f"  Serveur  : {cfg['base_url']}")
    print(f"  Stream   : {'oui' if cfg['stream'] else 'non'}")
    print(f"  Mémoire  : {'longue activée (' + str(long_term.count) + ' souvenirs)' if long_term else 'session uniquement'}")
    print()
    print("  Tapez /help pour la liste des commandes.")
    print_separator()

    turn = 0

    while True:
        try:
            user_input = input("\n😝 Vous : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Au revoir !")
            if cfg["show_metrics"]:
                print_metrics(session)
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        # --- Commandes spéciales ---

        if cmd in ("/quit", "/exit"):
            print("\n👋 Au revoir !")
            if cfg["show_metrics"]:
                print_metrics(session)
            break

        elif cmd == "/clear":
            memory.clear()
            print("🗑️  Historique de session effacé (les souvenirs long terme sont conservés).")
            continue

        elif cmd == "/history":
            print("\n📋 Historique de session :")
            print(memory.summary())
            continue

        elif cmd == "/model":
            print(f"🤖 Modèle actif : {cfg['model']}")
            continue

        elif cmd == "/metrics":
            print_metrics(session)
            continue

        elif cmd == "/memory":
            if not long_term:
                print("Mémoire longue désactivée (long_term_enabled: false dans le YAML).")
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
                else:
                    print("  (aucun souvenir stocké)")
            continue

        elif cmd.startswith("/forget "):
            query = user_input[8:].strip()
            if not long_term:
                print("Mémoire longue désactivée.")
            elif not query:
                print("Usage : /forget <ce que vous voulez oublier>")
            else:
                n = long_term.forget(query)
                print(f"{n} souvenir(s) supprimé(s) pour : « {query} »")
            continue

        elif cmd == "/help":
            print(HELP_TEXT)
            continue

        # --- Guardrail entrée ---

        try:
            user_input = input_guard.validate(user_input)
        except TopicBlocked as e:
            print(f"\n🤖 {cfg['persona_name']} :")
            print("·" * 60)
            print(e.polite_reply)
            continue
        except GuardrailError as e:
            print(f"{e}")
            continue

        # --- Injection mémoire longue dans le system prompt ---

        if long_term:
            memory_block = long_term.build_memory_block(user_input)
            if memory_block:
                enriched_prompt = cfg["system_prompt"].rstrip() + "\n\n" + memory_block
                memory.update_system_prompt(enriched_prompt)

        memory.add_user(user_input)
        turn += 1

        print(f"\n🤖 {cfg['persona_name']} ({cfg['model']}) :")
        print_separator("·")

        try:
            with Timer() as t:
                if cfg["stream"]:
                    response = client.chat(
                        memory.get_messages(), stream=True, options=ollama_options
                    )
                else:
                    response = client.chat(
                        memory.get_messages(), stream=False, options=ollama_options
                    )
                    print(response)

        except OllamaError as e:
            print(f"\nErreur : {e}")
            memory._history.pop()
            continue

        response = output_guard.process(response)
        memory.add_assistant(response)

        # --- Stocker la paire Q/R en mémoire longue ---
        if long_term:
            long_term.store(
                user_msg=user_input,
                assistant_msg=response,
            )

        metrics = TurnMetrics(
            turn_index=turn,
            input_chars=len(user_input),
            output_chars=len(response),
            latency_s=t.elapsed_s,
            model=cfg["model"],
        )
        session.record(metrics)

        if cfg["show_metrics"]:
            print_separator("·")
            tokens_in_ctx = memory.estimate_tokens()
            print(
                f"⏱  {metrics.latency_s:.2f}s | "
                f"{metrics.output_chars} chars | "
                f"{metrics.chars_per_second:.0f} c/s | "
                f"~{tokens_in_ctx} tokens en contexte"
            )



# Sous-commande : lister les modèles


def cmd_list_models(cfg: dict) -> None:
    client = OllamaClient(base_url=cfg["base_url"], model=cfg["model"], timeout=10.0)
    try:
        models = client.list_models()
    except OllamaError as e:
        print(f"{e}")
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

    config_raw = load_config(args.config)
    cfg = merge_config(config_raw, args)

    if args.list_models:
        cmd_list_models(cfg)
        return

    run_interactive(cfg)


if __name__ == "__main__":
    main()