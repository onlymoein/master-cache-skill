-- Lease-protected cache fill (Redis/Valkey). Rejects a stale set that races a delete.
--
-- Protocol (references/core/invalidation-consistency.md):
--   miss   -> SET lease:{key} <token> NX PX 10000      (only one filler gets the lease)
--   filler -> load from the source, then EVALSHA this script
--   write  -> DEL {key} lease:{key}                     (revokes any in-flight filler's right to set)
--
-- KEYS[1] = cache key
-- KEYS[2] = lease key (lease:{key}); same hash slot as KEYS[1] in Redis Cluster: use {key} hash tags
-- ARGV[1] = lease token the filler was given
-- ARGV[2] = value to store
-- ARGV[3] = TTL in milliseconds (add jitter in the caller, e.g. ttl * (0.9 + 0.2 * rand))
--
-- Returns 1 when stored, 0 when the lease was revoked or taken over (value not stored).

if redis.call('GET', KEYS[2]) == ARGV[1] then
  redis.call('SET', KEYS[1], ARGV[2], 'PX', tonumber(ARGV[3]))
  redis.call('DEL', KEYS[2])
  return 1
end
return 0
