from __future__ import annotations

import argparse
import json
from pathlib import Path


def train_compact_adapter(
    domain: str,
    samples_path: str | Path,
    output_path: str | Path,
    epochs: int = 120,
) -> Path:
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required. Install requirements-neural.txt in the active virtual environment."
        ) from exc

    samples = [
        json.loads(line)
        for line in Path(samples_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(samples) < 2:
        raise ValueError("At least two training samples are required.")
    features = torch.tensor([item["features"] for item in samples], dtype=torch.float32)
    targets = torch.tensor([item["targets"] for item in samples], dtype=torch.float32)
    hidden = max(8, min(64, features.shape[1] * 2))
    model = nn.Sequential(
        nn.Linear(features.shape[1], hidden),
        nn.GELU(),
        nn.Dropout(0.05),
        nn.Linear(hidden, targets.shape[1]),
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss()
    model.train()
    loss_value = 0.0
    for _ in range(max(1, epochs)):
        optimizer.zero_grad()
        loss = criterion(model(features), targets)
        loss.backward()
        optimizer.step()
        loss_value = float(loss.detach())
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "domain": domain,
            "state_dict": model.state_dict(),
            "input_size": features.shape[1],
            "hidden_size": hidden,
            "output_size": targets.shape[1],
            "sample_count": len(samples),
            "final_loss": loss_value,
            "target_labels": samples[0].get("target_labels", []),
        },
        output,
    )
    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_type": "compact_neural_adapter",
                "domain": domain,
                "weights": str(output),
                "sample_count": len(samples),
                "final_loss": loss_value,
                "input_size": features.shape[1],
                "hidden_size": hidden,
                "output_size": targets.shape[1],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anime-compact-neural-trainer")
    parser.add_argument("--domain", required=True, choices=("camera", "lighting"))
    parser.add_argument("--samples", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = train_compact_adapter(args.domain, args.samples, args.output, args.epochs)
    print(f"Trained compact neural adapter: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
