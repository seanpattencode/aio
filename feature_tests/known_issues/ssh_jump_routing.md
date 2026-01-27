# SSH Jump Host Routing (Future Idea)

## Problem
Some hosts are unreachable directly due to network segmentation (AP isolation, VPNs, firewalls) but reachable via another host.

## SSH Built-in Support
```bash
ssh -J jump_user@jump_host target_user@target -p 8022
ssh -J hostA,hostB,hostC target  # multi-hop
```

## Potential `aio ssh` Integration

### Level 1: Manual Jump (~10 tokens)
```bash
aio ssh 1 -j 2   # reach termux(1) via hsu(2)
```
```python
if '-j' in sys.argv:
    j = hosts[int(sys.argv[sys.argv.index('-j')+1])][1]
    cmd = ['ssh', '-J', j, ...]
```

### Level 2: Auto Single Hop (~50-80 tokens)
If target unreachable, try via each reachable host:
```python
if not _up(target):
    for name, jump in hosts:
        if _up(jump):
            # SSH to jump, test if it can reach target
            r = sp.run(['ssh', jump, f'nc -z {target_ip} {target_port}'])
            if r.returncode == 0:
                use_jump(jump)
                break
```

### Level 3: Auto Path Discovery (~200+ tokens)
Build connectivity graph, find shortest path:
```
Hosts: A, B, C, D
Edges: A-B, B-C, C-D
Query: path from A to D = A→B→C→D
```

Requires:
1. Query each reachable host for its reachable hosts
2. Build adjacency graph
3. BFS for shortest path
4. Chain: `ssh -J B,C D`

## Complexity vs Value
- Level 1: Low effort, covers 90% of cases
- Level 2: Medium effort, automatic but slow (tests each host)
- Level 3: High effort, rarely needed

## Decision
Not implementing now. Manual workaround exists:
```bash
ssh -J user@jump_host user@target -p 8022
```

Document for future if demand arises.
