#!/usr/bin/env python3
"""
scripts/analyze_traces.py -- Analyse des traces JSONL Atlas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

import pandas as pd

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# exemple de pricing avec GPT-4o
GPT4O_INPUT_PRICE_PER_1K  = 0.005   # $ / 1k tokens input
GPT4O_OUTPUT_PRICE_PER_1K = 0.015   # $ / 1k tokens output


def load_traces(path: Path) -> pd.DataFrame:
    if not path.exists():
        sys.exit(f"Fichier de traces introuvable : {path}\n"
                 "Lancez atlas-chat et faites quelques échanges d'abord.")
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if not records:
        sys.exit("Le fichier de traces est vide.")
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def print_header(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def analyze(df: pd.DataFrame, no_plot: bool) -> None:

    print_header(f"Analyse de {len(df)} traces -- modèle(s) : {', '.join(df['model'].unique())}")

    # 1. Latence
    print_header("1. Latence (ms)")
    lat = df["latency_ms"]
    print(f"  Minimum   : {lat.min():.0f} ms")
    print(f"  Médiane   : {lat.median():.0f} ms")
    print(f"  Moyenne   : {lat.mean():.0f} ms")
    print(f"  p95       : {lat.quantile(0.95):.0f} ms")
    print(f"  Maximum   : {lat.max():.0f} ms")

    # 2. Top 5 requêtes les plus longues
    print_header("2. Top 5 requêtes les plus lentes")
    top5 = df.nlargest(5, "latency_ms")[["timestamp", "latency_ms", "user_message", "model"]]
    for _, row in top5.iterrows():
        ts = row["timestamp"].strftime("%d/%m %H:%M")
        msg = str(row["user_message"])[:60]
        print(f"  {row['latency_ms']:6.0f} ms | {ts} | {msg}")

    # 3. Distribution des tokens de prompt
    print_header("3. Tokens de prompt")
    pt = df["prompt_tokens"]
    if pt.sum() == 0:
        print("  (tokens non disponibles -- requiert le mode non-streaming)")
    else:
        print(f"  Médiane   : {pt.median():.0f} tokens")
        print(f"  p95       : {pt.quantile(0.95):.0f} tokens")
        print(f"  Total     : {pt.sum():.0f} tokens sur {len(df)} échanges")
        print(f"  Moyenne contexte : {pt.mean():.0f} tokens/tour")

    # 4. Coût estimé GPT-4o
    print_header("4. Coût estimé si GPT-4o")
    total_pt = df["prompt_tokens"].sum()
    total_ct = df["completion_tokens"].sum()
    if total_pt == 0:
        print("  (tokens non disponibles)")
    else:
        cost_in  = (total_pt  / 1000) * GPT4O_INPUT_PRICE_PER_1K
        cost_out = (total_ct  / 1000) * GPT4O_OUTPUT_PRICE_PER_1K
        cost_total = cost_in + cost_out
        print(f"  Input  : {total_pt:,} tokens  → ${cost_in:.4f}")
        print(f"  Output : {total_ct:,} tokens  → ${cost_out:.4f}")
        print(f"  Total  : ${cost_total:.4f}  (vs $0.00 avec Ollama local)")
        print(f"  Economie : 100% -- modèle local = aucun coût variable")

    # 5. Guardrails déclenchés
    print_header("5. Guardrails déclenchés")
    all_rules: list[str] = []
    for rules in df["guardrails_triggered"]:
        if isinstance(rules, list):
            all_rules.extend(rules)
    if not all_rules:
        print("  Aucun guardrail déclenché.")
    else:
        from collections import Counter
        for rule, count in Counter(all_rules).most_common():
            print(f"  {rule:<30} : {count}x")

    # 6. Mémoire longue
    print_header("6. Mémoire longue (souvenirs injectés)")
    hits = df["memory_hits"]
    print(f"  Tours avec souvenirs : {(hits > 0).sum()} / {len(df)}")
    if hits.sum() > 0:
        print(f"  Moyenne par tour     : {hits.mean():.1f}")
        print(f"  Maximum              : {hits.max()}")

    # Graphiques
    
    if not no_plot and HAS_MATPLOTLIB:
        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        fig.suptitle("Atlas -- Analyse des traces", fontsize=14)

        # Latence
        axes[0].hist(df["latency_ms"], bins=20, color="steelblue", edgecolor="white")
        axes[0].axvline(lat.median(), color="red", linestyle="--", label=f"Médiane {lat.median():.0f}ms")
        axes[0].axvline(lat.quantile(0.95), color="orange", linestyle="--", label=f"p95 {lat.quantile(0.95):.0f}ms")
        axes[0].set_title("Distribution latence (ms)")
        axes[0].legend(fontsize=8)

        # Tokens
        if df["prompt_tokens"].sum() > 0:
            axes[1].plot(df["prompt_tokens"].values, marker="o", markersize=3, color="teal")
            axes[1].set_title("Tokens de prompt par tour")
            axes[1].set_xlabel("Tour")
        else:
            axes[1].text(0.5, 0.5, "Tokens\nnon disponibles", ha="center", va="center")
            axes[1].set_title("Tokens de prompt")

        # Guardrails
        if all_rules:
            from collections import Counter
            counts = Counter(all_rules)
            axes[2].barh(list(counts.keys()), list(counts.values()), color="salmon")
            axes[2].set_title("Guardrails déclenchés")
        else:
            axes[2].text(0.5, 0.5, "Aucun\nguardrail", ha="center", va="center")
            axes[2].set_title("Guardrails déclenchés")

        plt.tight_layout()
        out = _ROOT / "data" / "traces_analysis.png"
        out.parent.mkdir(exist_ok=True)
        plt.savefig(out, dpi=150)
        print(f"\n  Graphique sauvegardé : {out}")
        plt.show()
    elif not HAS_MATPLOTLIB:
        print("\n  (installez matplotlib pour les graphiques : pip install matplotlib)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse des traces JSONL Atlas")
    parser.add_argument("--file", default=None, help="Chemin vers le fichier JSONL")
    parser.add_argument("--no-plot", action="store_true", help="Désactiver les graphiques")
    args = parser.parse_args()

    path = Path(args.file) if args.file else _ROOT / "data" / "traces.jsonl"
    df = load_traces(path)
    analyze(df, no_plot=args.no_plot)


if __name__ == "__main__":
    main()