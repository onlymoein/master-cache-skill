-- Version-conditional cache set (Redis/Valkey): never overwrite a newer value with an older one.
--
-- Store values as a hash {v = <version>, d = <data>}. The version must come from the same read
-- as the data (row version column, updated_at in microseconds, or a CDC/LSN position).
--
-- KEYS[1] = cache key
-- ARGV[1] = version of the value being written (integer)
-- ARGV[2] = serialized data
-- ARGV[3] = TTL in milliseconds (add jitter in the caller)
--
-- Returns 1 when stored, 0 when the cache already holds the same or a newer version.
--
-- Read side:  HMGET key v d   -> use d when present
-- Delete:     DEL key         (a later fill with any version can then set it again)

local current = redis.call('HGET', KEYS[1], 'v')
if current and tonumber(current) >= tonumber(ARGV[1]) then
  return 0
end
redis.call('HSET', KEYS[1], 'v', ARGV[1], 'd', ARGV[2])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[3]))
return 1
