"""10-second multi-GPU sanity check: all-reduce over NCCL. Run with torchrun."""
import os

import torch
import torch.distributed as dist

dist.init_process_group("nccl")
rank = dist.get_rank()
torch.cuda.set_device(int(os.environ["LOCAL_RANK"]))
x = torch.ones(1 << 20, device="cuda") * (rank + 1)
dist.all_reduce(x)
expected = sum(range(1, dist.get_world_size() + 1))
assert torch.allclose(x, torch.full_like(x, expected)), (x[0].item(), expected)
if rank == 0:
    print(f"ddp_check OK: world_size={dist.get_world_size()}", flush=True)
dist.destroy_process_group()
