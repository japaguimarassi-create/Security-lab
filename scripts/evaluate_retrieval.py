import argparse
import json
from pathlib import Path
from klod.embeddings import EmbeddingEngine
from klod.knowledge import KnowledgeStore

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="./data/klod.sqlite3")
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if not args.queries.is_file():
        raise SystemExit(f"Query set not found: {args.queries}")
    embedder = EmbeddingEngine(args.model, args.device)
    store = KnowledgeStore(args.database)
    reciprocal_ranks, hits, total = [], 0, 0
    with args.queries.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            row = json.loads(line)
            required = {"namespace", "query", "expected_source_url"}
            if not required.issubset(row):
                raise SystemExit(f"{args.queries}:{line_number}: missing {required - set(row)}")
            vector = embedder.encode_query(row["query"])
            results = store.search_hybrid(
                row["namespace"], row["query"], vector, args.model, args.k)
            rank = next((index for index, item in enumerate(results, 1)
                         if item["source_url"] == row["expected_source_url"]), None)
            total += 1
            if rank is not None:
                hits += 1
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)
    report = {"queries": total, f"recall_at_{args.k}": hits / max(1, total),
              "mrr_at_k": sum(reciprocal_ranks) / max(1, total),
              "embedding_model": args.model, "database": args.database}
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
