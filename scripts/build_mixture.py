import argparse
import json
import random
from contextlib import ExitStack
from pathlib import Path
import yaml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/data_mixture.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/mixture.jsonl"))
    parser.add_argument("--max-documents", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    sources = cfg.get("sources", [])
    if not sources or args.max_documents < 1:
        raise SystemExit("Mixture needs sources and a positive --max-documents")
    for source in sources:
        if float(source.get("weight", 0)) <= 0:
            raise SystemExit(f"Invalid weight for source {source.get('name')}")
        if not Path(source["path"]).is_file():
            raise SystemExit(f"Missing source file: {source['path']}")
    rng = random.Random(args.seed)
    counts = {source["name"]: 0 for source in sources}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        streams = {
            source["name"]: {"source": source, "handle": stack.enter_context(
                Path(source["path"]).open(encoding="utf-8"))}
            for source in sources
        }
        with args.output.open("w", encoding="utf-8") as output:
            while streams and sum(counts.values()) < args.max_documents:
                names = list(streams)
                weights = [float(streams[name]["source"]["weight"]) for name in names]
                selected = rng.choices(names, weights=weights, k=1)[0]
                line = streams[selected]["handle"].readline()
                if not line:
                    streams.pop(selected)
                    continue
                row = json.loads(line)
                if not isinstance(row.get("text"), str) or not row["text"].strip():
                    continue
                row["mixture_source"] = selected
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[selected] += 1
    result = {"documents": sum(counts.values()), "counts": counts,
              "seed": args.seed, "output": str(args.output)}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
