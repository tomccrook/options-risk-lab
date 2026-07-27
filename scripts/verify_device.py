"""Explicit device eligibility probe; never silently switches training devices."""

import argparse
import json
import platform
import time

import torch

parser = argparse.ArgumentParser()
parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
args = parser.parse_args()
record = {
    "platform": platform.platform(),
    "torch": torch.__version__,
    "built_cuda": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "requested_device": args.device,
}
if args.device == "cuda":
    if not torch.cuda.is_available():
        raise SystemExit(
            "CUDA is unavailable for this locked environment. CPU research remains usable."
        )
    record["name"] = torch.cuda.get_device_name(0)
    record["capability"] = torch.cuda.get_device_capability(0)
    record["supported_architectures"] = torch.cuda.get_arch_list()
    major, minor = torch.cuda.get_device_capability(0)
    if f"sm_{major}{minor}" not in torch.cuda.get_arch_list():
        raise SystemExit(
            "GPU architecture absent from this wheel; verify official compatible build."
        )
model = torch.nn.Sequential(torch.nn.Linear(5, 48), torch.nn.Tanh(), torch.nn.Linear(48, 1))
model = model.to(device=args.device, dtype=torch.float64)
x = torch.rand(2048, 5, device=args.device, dtype=torch.float64, requires_grad=True)
start = time.perf_counter()
y = model(x).sum()
delta = torch.autograd.grad(y, x, create_graph=True)[0]
gamma = torch.autograd.grad(delta[:, 0].sum(), x)[0]
if args.device == "cuda":
    torch.cuda.synchronize()
assert torch.isfinite(gamma).all()
record["second_derivative_workload_ms"] = (time.perf_counter() - start) * 1000
record["scope"] = (
    "Eligibility workload, not a fair study benchmark or authorization to change devices"
)
print(json.dumps(record, indent=2))
