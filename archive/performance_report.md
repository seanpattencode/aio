
## Performance Statistics

System performance metrics collected during testing:

| Metric | Average | Median | Min | Max | 95th % | Status |
|--------|---------|--------|-----|-----|--------|--------|
| Startup Time | 28.10ms | 27.71ms | 24.69ms | 36.81ms | 38.01ms | ✓ |
| Shutdown Time | 835.97ms | 1001.27ms | 7.30ms | 1003.36ms | 1004.67ms | ⚠️ |
| Restart Time | 904.05ms | 1028.98ms | 24.82ms | 1032.96ms | 1033.55ms | ⚠️ |
| Memory Usage | 16.07MB | 16.08MB | 15.40MB | 16.57MB | 16.63MB | ✓ |
| CPU Usage | 2.50% | 0.00% | 0.00% | 10.00% | 10.00% | ✓ |

### Resilience Testing

- **Total Random Restarts**: 8
- **Test Duration**: 30 seconds
- **Result**: ✓ System survived all random restarts

### Performance Requirements

- All operations must complete within **100ms**
- **Status**: ⚠️  Some operations exceed 100ms limit
