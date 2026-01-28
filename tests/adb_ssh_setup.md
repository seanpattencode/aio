# ADB SSH Setup for Termux

Test commands for `aio ssh self <name>` via ADB connection.

## Prerequisites
- Device connected via ADB
- Termux with sshd running (`pkg install openssh && sshd`)
- Host SSH key exists (`~/.ssh/id_ed25519.pub`)

## Setup Flow

### 1. Forward SSH port via ADB
```bash
# Forward local 8022 to device 8022
adb forward tcp:8022 tcp:8022

# Verify port open
nc -z localhost 8022 && echo "Port open"
```

### 2. Get device username
```bash
# Type command in Termux, save output to /sdcard/
adb shell 'input text "whoami%s>%s/sdcard/out.txt"'
adb shell input keyevent 66
sleep 1
adb shell 'cat /sdcard/out.txt'
# Returns: u0_a717 (or similar)
```

### 3. Add SSH public key to device
```bash
# Get local public key
cat ~/.ssh/id_ed25519.pub

# Add to Termux authorized_keys via input text
adb shell 'input text "mkdir%s-p%s~/.ssh%s&&%secho%sssh-ed25519%sAAAAC3...%s>>%s~/.ssh/authorized_keys%s&&%schmod%s600%s~/.ssh/authorized_keys"'
adb shell input keyevent 66
```

### 4. Test SSH connection
```bash
# Connect via forwarded port with key auth
ssh -o StrictHostKeyChecking=no -o PasswordAuthentication=no -p 8022 u0_a717@localhost 'echo connected'
```

### 5. Run aio ssh self
```bash
# With password argument (non-interactive)
ssh -p 8022 u0_a717@localhost 'aio ssh self pixel7pro Focus999.'

# Verify entry created
ssh -p 8022 u0_a717@localhost 'aio ssh'
```

## Database Sync

### Check events on device
```bash
ssh -p 8022 u0_a717@localhost 'grep pixel7pro ~/.local/share/aios/events.jsonl'
```

### Sync device to remote
```bash
# Configure git if needed
ssh -p 8022 u0_a717@localhost 'git config --global user.email "a@a" && git config --global user.name "aio"'

# Pull, merge, push
ssh -p 8022 u0_a717@localhost 'cd ~/.local/share/aios && git pull origin main --no-rebase -X theirs && git push origin master:main'
```

### Pull to local
```bash
cd ~/.local/share/aios && git pull origin main

# Verify event synced
grep pixel7pro events.jsonl

# Run aio ssh to trigger replay_events()
aio ssh
```

## Direct Database Operations

### Check SSH entries via sqlite3
```bash
sqlite3 ~/.local/share/aios/aio.db "SELECT name,host FROM ssh"
```

### Check via python (handles WAL mode)
```bash
python3 -c "import sqlite3; print(list(sqlite3.connect('~/.local/share/aios/aio.db'.replace('~',__import__('os').path.expanduser('~'))).execute('SELECT name,host FROM ssh')))"
```

### Insert entry directly
```bash
sqlite3 ~/.local/share/aios/aio.db "INSERT INTO ssh(name,host,pw) VALUES('pixel7pro','u0_a717@192.168.1.202:8022','Rm9jdXM5OTku')"
```

## Host Key Issues

### Remove stale host key
```bash
ssh-keygen -f ~/.ssh/known_hosts -R '[192.168.1.202]:8022'
```

## Common Commands

```bash
# Update aio on device
aio ssh 6 'aio update -y'

# Run command on device
aio ssh 6 'whoami'

# Check device IP
adb shell 'getprop ro.product.model'
```

## Sync Architecture

```
Device: aio ssh self pixel7pro
    ↓
emit_event() → writes to events.jsonl
    ↓
db_sync() → git add, commit, fetch, merge, push
    ↓
Remote: github repo (aio-sync)
    ↓
Local: git pull origin main
    ↓
replay_events() → rebuilds sqlite from events.jsonl
```

### Why Direct SQL Inserts Disappear

When you run `aio ssh`, it calls:
```python
init_db(); db_sync(pull=True)  # ssh.py line 13
```

`db_sync(pull=True)` calls `replay_events()` which:
```python
c.execute("DELETE FROM ssh")  # wipes table
# rebuilds only from events.jsonl
```

Direct sqlite inserts get erased on next command. Always use `emit_event()`.

## Root Cause: Branch Mismatch + Git Conflicts

### 1. Device tracked `master`, remote used `main`
- Device commits went to local `master` branch
- Remote repo expects pushes to `main`
- `git push` silently did nothing

### 2. No git user configured on device
- When device tried to merge, git failed with "Committer identity unknown"
- Merge aborted, events stayed local

### 3. Merge conflicts on db files
- `.gitignore` wasn't properly excluding `aio.db` and `timing.jsonl`
- These binary/large files conflicted between devices
- `git merge -X theirs` couldn't auto-resolve modify/delete conflicts

### Fix Applied
```bash
# Configure git on device
git config --global user.email "a@a" && git config --global user.name "aio"

# Resolve conflicts and push to correct branch
cd ~/.local/share/aios
git checkout --theirs .
git add -A && git commit -m "merge"
git push origin master:main  # push local master → remote main
```

## Troubleshooting

### EOF error on input()
- Pass password as argument: `aio ssh self name password`
- Or ensure stdin is a tty

### Events not syncing
- Check git status on device: `cd ~/.local/share/aios && git status`
- Device may track `master` while remote is `main`
- Force push: `git push origin master:main`

### replay_events() deletes entries
- `db_sync(pull=True)` calls `replay_events()` which rebuilds tables from events.jsonl
- Direct sqlite inserts get overwritten
- Always use `emit_event()` for persistent changes

---

## Comparison: Current System vs Industry Solutions

### Current aio Sync System
```
events.jsonl (append-only log) → git push/pull → replay_events() → SQLite cache
```

**Pros:**
- Simple, no external dependencies beyond git
- Human-readable event log
- Works with any git host (GitHub, self-hosted)

**Cons:**
- Manual conflict resolution needed
- Full table rebuild on sync (DELETE + INSERT all)
- Branch mismatches cause silent failures
- No real-time sync
- Binary db files cause merge conflicts

### Industry Alternatives

| Solution | Type | Effort | Best For |
|----------|------|--------|----------|
| [CR-SQLite](https://github.com/vlcn-io/cr-sqlite) | CRDT extension | Low | Drop-in SQLite replacement |
| [SQLite Sync](https://github.com/sqliteai/sqlite-sync) | CRDT extension | Low | Real-time collaboration |
| [ElectricSQL](https://electric-sql.com) | Postgres↔SQLite | Medium | Cloud-backed apps |
| [Litestream](https://litestream.io) | WAL streaming | Low | Backup/restore only |
| [PouchDB](https://pouchdb.com) | CouchDB sync | Medium | Full rewrite to NoSQL |

### Recommended: CR-SQLite

**Why:** Minimal code change, automatic conflict resolution.

```python
# Current
c.execute("INSERT INTO ssh VALUES(?,?,?)", (n,h,pw))
emit_event("ssh","add",{...})  # manual event tracking
db_sync()  # git-based sync

# With CR-SQLite
c.execute("SELECT crsql_as_crr('ssh')")  # one-time setup
c.execute("INSERT INTO ssh VALUES(?,?,?)", (n,h,pw))
# Sync handled automatically via changesets
```

**Features:**
- Tables become CRRs (Conflict-free Replicated Relations)
- Column-level merging (edit different columns = no conflict)
- 2.5x slower inserts (acceptable for config data)
- Works offline, syncs when connected

### Migration Path

1. Keep events.jsonl as audit log (optional)
2. Replace `replay_events()` with CR-SQLite merge
3. Remove git-based db sync (keep for code only)
4. Sync via simple HTTP POST of changesets

```bash
# Install
pip install crsqlite  # or load extension
```

Sources:
- [CR-SQLite GitHub](https://github.com/vlcn-io/cr-sqlite)
- [SQLite Sync](https://github.com/sqliteai/sqlite-sync)
- [ElectricSQL](https://electric-sql.com)
- [CRDT Implementations](https://crdt.tech/implementations)

---

## How Big Tech Does Sync

### 1. Chrome Sync

**Architecture:** Client-server with protobuf protocol

```
Chrome Client                         Google Servers
     │                                      │
     ├─── DataTypeSyncBridge ───────────────┤
     │    (bookmarks, tabs, etc)            │
     │                                      │
     ├─── HTTP POST to clients4.google.com ─┤
     │    (protobuf body + Bearer token)    │
     │                                      │
     └─── XMPP push notification ◄──────────┘
          (Google Talk servers)
```

**Key Components:**
- **DataTypeSyncBridge**: Each data type (bookmarks, passwords, tabs) implements this interface
- **EntityMetadata**: Per-entity sync state (version, hash, timestamps)
- **DataTypeState**: Per-type state (progress marker for incremental sync)
- **Unified Sync and Storage (USS)**: Metadata stored atomically with data

**Sync Flow:**
1. Local change → `Put()` to processor
2. Processor batches changes, sends HTTP POST with protobuf
3. Server stores, broadcasts XMPP invalidation to other devices
4. Other clients receive push, call `ApplyIncrementalSyncChanges()`

**Conflict Resolution:** Last-write-wins with version vectors

**Encryption:** AES-256-GCM keyed to Google Account

Sources: [Chrome Sync Design](https://www.chromium.org/developers/design-documents/sync/), [Model API](https://www.chromium.org/developers/design-documents/sync/model-api/), [Protocol Analysis](https://damian.fyi/2014/02/09/inside-chrome-sync/)

---

### 2. Facebook TAO (The Associations and Objects)

**Architecture:** Graph store with 2-tier caching

```
                    ┌─────────────────┐
                    │   TAO Clients   │
                    │  (L1 Cache)     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Memcache │   │ Memcache │   │ Memcache │
        │ (L2)     │   │ (L2)     │   │ (L2)     │
        └────┬─────┘   └────┬─────┘   └────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                    ┌───────────────┐
                    │    MySQL      │
                    │   (sharded)   │
                    └───────────────┘
```

**Data Model:**
- **Objects**: Nodes (users, posts, photos) with typed properties
- **Associations**: Edges (friendships, likes, comments) with id1→id2

**Sharding Strategy:**
- Associations stored on same shard as `id1`
- Enables single-DB queries for "get all comments on post X"

**Sync Mechanisms:**
| Mechanism | Purpose |
|-----------|---------|
| Write-through cache | Client updates local cache before sending to server |
| Cache invalidation | Server broadcasts invalidate to all clients |
| Read repair | Client detects stale data, fetches fresh |
| Inverse sync | Bidirectional edges kept in sync automatically |

**Consistency:** Eventually consistent, read-optimized
- 86.3% reads use relaxed consistency
- 13.7% require strong consistency
- Quorum: 2 of 4 replicas for reads

**Scale:** Billions of reads/sec, millions of writes/sec, petabytes of data

Sources: [TAO Paper (USENIX)](https://www.usenix.org/conference/atc13/technical-sessions/presentation/bronson), [TAO Overview](https://engineering.fb.com/2013/06/25/core-infra/tao-the-power-of-the-graph/), [Deep Dive](https://www.micahlerner.com/2021/10/13/tao-facebooks-distributed-data-store-for-the-social-graph.html)

---

### 3. WhatsApp Multi-Device Sync

**Architecture:** Client-fanout with E2E encryption

```
Sender Device                              Recipient Devices
     │                                     ┌─────────────┐
     │    ┌─────────────────────┐          │  Phone      │
     ├───►│  Encrypt N times    │─────────►│  (Device 1) │
     │    │  (one per device)   │          ├─────────────┤
     │    └─────────────────────┘          │  Laptop     │
     │              │                      │  (Device 2) │
     │              ▼                      ├─────────────┤
     │    ┌─────────────────────┐          │  Tablet     │
     │    │  WhatsApp Server    │─────────►│  (Device 3) │
     │    │  (routing only,     │          └─────────────┘
     │    │   no decryption)    │
     │    └─────────────────────┘
```

**Cryptographic Foundation (Signal Protocol):**
- **Curve25519**: Key agreement
- **AES-256**: Message encryption
- **HMAC-SHA256**: Authentication
- **Double Ratchet**: Forward secrecy (new keys per message)
- **3-DH Handshake**: Initial key exchange

**Multi-Device Key Management:**
```
Before: 1 identity key per user
After:  1 identity key per DEVICE

Account ──┬── Phone (Identity Key A)
          ├── Laptop (Identity Key B)
          ├── Tablet (Identity Key C)
          └── Web (Identity Key D)
```

**Device Linking:**
1. Primary signs companion's Identity Key → Account Signature
2. Companion signs primary's Identity Key → Device Signature
3. Both signatures verified → E2E sessions established

**Message Sync (Client-Fanout):**
1. Sender encrypts message N times (once per recipient device)
2. Each encrypted copy uses unique pairwise session
3. Server routes to devices, deletes after delivery
4. Server CANNOT decrypt (no keys)

**Security Properties:**
- Device compromise doesn't expose other devices' messages
- History transfer between devices is E2E encrypted
- Users can verify device list (detect malicious additions)

**Group Chats:**
- Sender Key scheme (one encryption, N recipients)
- Sender Key distributed via pairwise sessions

Sources: [WhatsApp Multi-Device](https://engineering.fb.com/2021/07/14/security/whatsapp-multi-device/), [Signal Protocol](https://en.wikipedia.org/wiki/Signal_Protocol), [WhatsApp Encryption Whitepaper](https://faq.whatsapp.com/820124435853543)

---

## Comparison Summary

| Aspect | Chrome Sync | Facebook TAO | WhatsApp | aio (current) |
|--------|-------------|--------------|----------|---------------|
| **Model** | Per-type bridges | Graph (objects + edges) | Client-fanout | Event log |
| **Transport** | HTTP + XMPP push | Internal RPC | E2E encrypted | Git |
| **Storage** | Server-authoritative | MySQL shards + cache | Device-only | SQLite + events.jsonl |
| **Conflict** | Last-write-wins | Eventually consistent | No conflicts (E2E) | Manual merge |
| **Encryption** | AES-256-GCM (server has keys) | None (internal) | E2E (server blind) | None |
| **Offline** | Queue + sync | N/A (always online) | Full offline | Full offline |
| **Scale** | Millions | Billions/sec | Billions | Single user |

## What aio Could Adopt

1. **From Chrome:** Per-type sync bridges with metadata (instead of full replay)
2. **From TAO:** Write-through cache + invalidation (instead of full rebuild)
3. **From WhatsApp:** Client-fanout for multi-device (each device gets own encrypted copy)

**Simplest improvement:** Replace git-based sync with HTTP POST of changesets (like Chrome), use CR-SQLite for conflict resolution (like TAO's eventual consistency).

---

### 4. Email: IMAP Protocol

**Architecture:** Server-authoritative with client cache

```
Email Client                              Mail Server
     │                                         │
     ├──── TCP:993 (TLS) ─────────────────────►│
     │                                         │
     │◄─── Folder list + message headers ──────┤
     │                                         │
     ├──── FETCH specific messages ───────────►│
     │                                         │
     │◄─── Full message content ───────────────┤
     │                                         │
     ├──── IDLE (keep connection open) ───────►│
     │                                         │
     │◄─── Push: "new message in INBOX" ───────┤
```

**Sync Model:**
- **Server is source of truth** - clients cache locally
- **Flags track state**: `\Seen`, `\Answered`, `\Deleted`, `\Flagged`
- **UIDs** (Unique IDs): Persistent message identifiers for offline sync
- **UIDVALIDITY**: Epoch marker - if changed, re-sync entire folder

**IMAP IDLE (Push):**
```
Client: A001 SELECT INBOX
Client: A002 IDLE
Server: + idling
        ... (connection held open) ...
Server: * 5 EXISTS        ← new message arrived
Client: DONE
Client: A003 FETCH 5 ...
```

**Limitations:**
- IDLE only watches ONE folder at a time
- Need separate connection per folder for real push
- Stateful TCP connection required
- Complex parser (not JSON)

Sources: [IMAP Wikipedia](https://en.wikipedia.org/wiki/Internet_Message_Access_Protocol), [IMAP Explained](https://mailtrap.io/blog/imap/)

---

### 5. Gmail Sync

**Architecture:** Hybrid (IMAP + proprietary API + mobile push)

```
┌─────────────────────────────────────────────────────────┐
│                      Gmail Backend                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │   IMAP   │    │ Gmail API│    │ Cloud Pub/Sub    │   │
│  │ :993     │    │ REST     │    │ (push webhooks)  │   │
│  └────┬─────┘    └────┬─────┘    └────────┬─────────┘   │
│       │               │                   │              │
└───────┼───────────────┼───────────────────┼──────────────┘
        │               │                   │
        ▼               ▼                   ▼
   Thunderbird      Web Apps            Mobile Apps
   Apple Mail      (OAuth)            (GCM/FCM push)
```

**Three Sync Methods:**

| Method | Latency | Use Case |
|--------|---------|----------|
| IMAP IDLE | High (seconds) | Desktop clients |
| Gmail API + Pub/Sub | Low (instant) | Web apps, servers |
| GCM/FCM | Instant | Android/iOS native |

**Gmail API Push Flow:**
```python
# 1. Watch mailbox
POST /gmail/v1/users/me/watch
{
  "topicName": "projects/myapp/topics/gmail",
  "labelIds": ["INBOX"]
}

# 2. Receive webhook notification (minimal payload)
{
  "emailAddress": "user@gmail.com",
  "historyId": "1234567"
}

# 3. Fetch actual changes using historyId
GET /gmail/v1/users/me/history?startHistoryId=1234560
# Returns: messagesAdded, messagesDeleted, labelsAdded, etc.
```

**Key Design Decisions:**
- **Minimal push payload**: Only `historyId`, not message content
- **Client fetches changes**: Reduces push bandwidth, enables batching
- **Rate limit**: Max 1 notification/sec per user
- **History API**: Incremental sync from any point (like Chrome's progress markers)

Sources: [Gmail Push Notifications](https://developers.google.com/workspace/gmail/api/guides/push), [Gmail IMAP](https://developers.google.com/workspace/gmail/imap/imap-smtp)

---

### 6. JMAP: Modern Email Protocol (IMAP Replacement)

**Architecture:** JSON over HTTP with WebSocket push

```
Email Client                              JMAP Server
     │                                         │
     ├──── POST /jmap (JSON batch) ───────────►│
     │     [                                   │
     │       ["Email/get", {...}],             │
     │       ["Email/query", {...}],           │
     │       ["Mailbox/get", {...}]            │
     │     ]                                   │
     │                                         │
     │◄─── JSON response (all results) ────────┤
     │                                         │
     ├──── WebSocket: subscribe ──────────────►│
     │                                         │
     │◄─── Push: {"changed": {"Email": [...]}} │
```

**Why JMAP > IMAP:**

| Feature | IMAP | JMAP |
|---------|------|------|
| Format | Custom text protocol | JSON |
| Requests | One action per request | Batch multiple |
| Push | IDLE (one folder) | WebSocket (all changes) |
| Efficiency | ~20x more requests | Baseline |
| Server load | ~5x higher | Baseline |
| Send mail | Separate SMTP | Same protocol |

**Sync State Tracking:**
```json
// Request changes since last sync
{
  "using": ["urn:ietf:params:jmap:mail"],
  "methodCalls": [
    ["Email/changes", {
      "accountId": "abc",
      "sinceState": "abc123"  // ← like Chrome's progress marker
    }, "0"]
  ]
}

// Response: only what changed
{
  "methodResponses": [
    ["Email/changes", {
      "oldState": "abc123",
      "newState": "def456",
      "created": ["msg1", "msg2"],
      "updated": ["msg3"],
      "destroyed": ["msg4"]
    }, "0"]
  ]
}
```

**Adoption (2025):**
- Fastmail (production)
- Thunderbird (rolling out)
- Cyrus, Apache James, Stalwart servers

Sources: [JMAP.io](https://jmap.io/), [IETF JMAP](https://www.ietf.org/blog/jmap/), [JMAP vs IMAP](https://linagora.com/en/topics/what-are-differences-between-imap-and-jmap)

---

## Updated Comparison Summary

| Aspect | Chrome | TAO | WhatsApp | IMAP | Gmail API | JMAP | aio |
|--------|--------|-----|----------|------|-----------|------|-----|
| **Format** | Protobuf | Internal | E2E binary | Text | JSON | JSON | JSON events |
| **Transport** | HTTP+XMPP | RPC | Custom | TCP | HTTP+Pub/Sub | HTTP+WS | Git |
| **Batch** | Yes | Yes | N/A | No | Yes | Yes | No |
| **Push** | XMPP | Invalidation | Fanout | IDLE | Webhook | WebSocket | Poll |
| **Incremental** | Yes | Yes | N/A | UIDs | historyId | sinceState | No (full rebuild) |
| **Offline** | Queue | N/A | Full | Cache | Queue | Queue | Full |

## Key Pattern: Incremental Sync with State Markers

All modern systems use the same pattern:

```
Client stores: lastSyncState = "abc123"

Client: "Give me changes since abc123"
Server: "Here's what changed: +msg1, +msg2, -msg3, newState=def456"

Client stores: lastSyncState = "def456"
```

**aio currently does:**
```
Client: "Give me everything"
Server: "Here's all events"
Client: DELETE * FROM table; INSERT all events
```

**aio should do:**
```
Client stores: lastEventId = "0e9722de"
Client: "Give me events after 0e9722de"
Server: "Here's 3 new events, lastId=abc123"
Client: Apply only new events, store lastEventId = "abc123"
```

---

## Master Comparison Table

### Architecture Overview

| System | Company | Scale | Primary Use |
|--------|---------|-------|-------------|
| Chrome Sync | Google | 3B+ users | Browser data (bookmarks, passwords, tabs) |
| TAO | Meta | 2B+ users | Social graph (friends, posts, likes) |
| WhatsApp | Meta | 2B+ users | Encrypted messaging |
| IMAP | Standard | Universal | Email (legacy) |
| Gmail API | Google | 1.8B users | Email (modern) |
| JMAP | Fastmail/IETF | Growing | Email (next-gen) |
| CR-SQLite | Open source | Any | Local-first apps |
| aio | Personal | 1 user | CLI config sync |

### Technical Comparison

| Aspect | Chrome Sync | TAO | WhatsApp | IMAP | Gmail API | JMAP | CR-SQLite | aio |
|--------|-------------|-----|----------|------|-----------|------|-----------|-----|
| **Data Format** | Protobuf | Binary | E2E encrypted | Text | JSON | JSON | SQLite + CRDT | JSON events |
| **Transport** | HTTPS | Internal RPC | Custom TCP | TCP:993 | HTTPS | HTTPS+WS | Any | Git SSH |
| **Auth** | OAuth | Internal | Phone + keys | User/pass | OAuth | OAuth | N/A | SSH keys |
| **Push Method** | XMPP | Invalidation broadcast | Client fanout | IDLE | Pub/Sub webhook | WebSocket | Poll/custom | Git pull |
| **Push Latency** | ~1s | ~100ms | Instant | 1-30s | ~1s | ~100ms | N/A | Manual |
| **Conflict Resolution** | Last-write-wins | Eventual consistency | No conflicts (E2E) | Flags | Last-write-wins | Last-write-wins | CRDT auto-merge | Manual merge |
| **Offline Support** | Full queue | N/A (server) | Full | Cache only | Queue | Queue | Full | Full |
| **Incremental Sync** | progressMarker | Version vector | Per-device keys | UIDVALIDITY | historyId | sinceState | Merkle tree | None (full rebuild) |
| **Encryption** | AES-256 (server has key) | None | E2E (server blind) | TLS only | TLS + at-rest | TLS only | Optional | None |
| **Open Source** | Chromium (client) | No | No | Yes (protocol) | No | Yes | Yes | Yes |

### Sync State Tracking

| System | State Token | What It Tracks |
|--------|-------------|----------------|
| Chrome Sync | `progressMarker` | Last sync position per data type |
| TAO | Version vector | Per-object version numbers |
| WhatsApp | Device identity keys | Per-device message state |
| IMAP | `UIDVALIDITY` + `HIGHESTMODSEQ` | Folder epoch + last change |
| Gmail API | `historyId` | Mailbox-wide change sequence |
| JMAP | `sinceState` | Per-type state string |
| CR-SQLite | Merkle tree hash | Table content hash |
| aio | None | Full replay every time |

### Request Efficiency

| System | Requests for "check 5 folders" | Batch Support |
|--------|--------------------------------|---------------|
| IMAP | 5 (one per folder) | No |
| Gmail API | 1 (batch endpoint) | Yes |
| JMAP | 1 (JSON array) | Yes |
| Chrome Sync | 1 (all types together) | Yes |
| aio | 1 (git pull) | N/A |

---

## Real-World Usage Examples

### 1. Chrome Sync - Bookmark Added

```
User adds bookmark on laptop:

Laptop:
  DataTypeSyncBridge.Put({
    id: "bookmark_123",
    title: "GitHub",
    url: "https://github.com",
    parent: "folder_456"
  })

  → HTTP POST clients4.google.com/chrome-sync
    Body: protobuf { entities: [...], progress_marker: "abc" }

  ← Response: { new_progress_marker: "def", conflicts: [] }

Server:
  → XMPP push to all other devices: "sync now"

Phone (receives XMPP):
  → HTTP POST with progress_marker: "old_marker"
  ← Response: { entities: [bookmark_123], new_marker: "def" }

  DataTypeSyncBridge.ApplyIncrementalSyncChanges([bookmark_123])
```

### 2. Facebook TAO - Like a Post

```
User likes post_789:

Client:
  TAO.addAssociation(
    id1: "user_123",
    id2: "post_789",
    type: "LIKES",
    time: now()
  )

TAO Layer:
  1. Write-through: Update L1 cache immediately
  2. Forward to TAO server

TAO Server:
  1. Write to MySQL shard (same shard as user_123)
  2. Broadcast invalidation to all L1/L2 caches
  3. Update inverse: post_789.liked_by += user_123

Other clients viewing post_789:
  1. Receive invalidation
  2. Next read fetches fresh like count

Query "who liked this post?":
  TAO.getAssociations(id1: "post_789", type: "LIKED_BY")
  → Returns from cache or MySQL (single shard query)
```

### 3. WhatsApp - Send Message to Group

```
User sends "Hello" to group with 3 members (each has 2 devices = 6 devices):

Sender:
  1. Generate Sender Key for group (if first message)
  2. Encrypt "Hello" with Sender Key → ciphertext
  3. For each recipient device (6 total):
     - Encrypt Sender Key with pairwise session key
     - Send: { encrypted_sender_key, ciphertext }

Server:
  - Routes 6 encrypted blobs to 6 devices
  - Cannot decrypt any of them
  - Deletes after delivery

Recipient Device:
  1. Decrypt Sender Key using pairwise session
  2. Decrypt message using Sender Key
  3. Display "Hello"

If device added later:
  - New pairwise session established
  - New device identity key signed by account
  - History re-encrypted and transferred (E2E)
```

### 4. IMAP - Check for New Email

```
Client:
  A001 LOGIN user@example.com password
  A002 SELECT INBOX
  → * 5 EXISTS
  → * OK [UIDVALIDITY 12345] [HIGHESTMODSEQ 100]

  A003 IDLE
  → + idling

  ... (connection held open for 29 minutes) ...

  → * 6 EXISTS    ← Server: new message!

  DONE
  A004 UID FETCH 6:* (FLAGS ENVELOPE)
  → * 6 FETCH (UID 1001 FLAGS (\Recent) ENVELOPE (...))

  A005 UID FETCH 1001 BODY[]
  → * 6 FETCH (UID 1001 BODY[] {5000} ... message content ...)
```

### 5. Gmail API - Watch for Changes

```python
# 1. Set up watch (once per 7 days)
POST https://gmail.googleapis.com/gmail/v1/users/me/watch
{
  "topicName": "projects/myapp/topics/gmail-push",
  "labelIds": ["INBOX"]
}
→ { "historyId": "12345", "expiration": "1699999999000" }

# 2. Receive webhook (when email arrives)
POST https://myapp.com/gmail-webhook
{
  "message": {
    "data": base64({ "emailAddress": "user@gmail.com", "historyId": "12350" })
  }
}

# 3. Fetch changes since last known historyId
GET https://gmail.googleapis.com/gmail/v1/users/me/history?startHistoryId=12345
→ {
    "history": [
      { "messagesAdded": [{ "message": { "id": "msg123" }}] }
    ],
    "historyId": "12350"
  }

# 4. Fetch actual message
GET https://gmail.googleapis.com/gmail/v1/users/me/messages/msg123
→ { full message content }

# 5. Store new historyId for next sync
db.save(historyId: "12350")
```

### 6. JMAP - Sync Email Changes

```json
// Single request: get mailboxes + recent emails + changes since last sync
POST https://jmap.example.com/api
{
  "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
  "methodCalls": [
    ["Mailbox/get", { "accountId": "u1" }, "a"],
    ["Email/query", { "accountId": "u1", "filter": { "inMailbox": "inbox" }, "limit": 20 }, "b"],
    ["Email/get", { "accountId": "u1", "#ids": { "resultOf": "b", "path": "/ids" } }, "c"],
    ["Email/changes", { "accountId": "u1", "sinceState": "abc123" }, "d"]
  ]
}

// Single response: everything in one round trip
{
  "methodResponses": [
    ["Mailbox/get", { "list": [{ "id": "inbox", "name": "Inbox", "totalEmails": 1000 }] }, "a"],
    ["Email/query", { "ids": ["msg1", "msg2", "msg3"] }, "b"],
    ["Email/get", { "list": [{ "id": "msg1", "subject": "Hello", ... }] }, "c"],
    ["Email/changes", {
      "oldState": "abc123",
      "newState": "def456",
      "created": ["msg4"],
      "updated": [],
      "destroyed": []
    }, "d"]
  ]
}

// Next sync: only need Email/changes with sinceState: "def456"
```

### 7. CR-SQLite - Sync Between Devices

```python
# Device A: Insert row
conn.execute("INSERT INTO ssh (name, host) VALUES ('server1', 'user@1.2.3.4')")

# Get changes as changeset
changes = conn.execute("SELECT * FROM crsql_changes WHERE version > ?", (last_sync,))
# Returns: [{ table: "ssh", pk: "server1", col: "host", val: "user@1.2.3.4",
#             version: 5, site_id: "deviceA" }]

# Send to Device B (any transport: HTTP, WebSocket, file, etc.)
http.post("https://deviceB/sync", changes)

# Device B: Apply changes
for change in changes:
    conn.execute(
        "INSERT INTO crsql_changes VALUES (?,?,?,?,?,?)",
        (change.table, change.pk, change.col, change.val, change.version, change.site_id)
    )
# CR-SQLite auto-merges using CRDT rules (no conflicts!)

# Both devices now have identical data
```

### 8. aio Current - Full Rebuild

```python
# Device A: Add SSH host
emit_event("ssh", "add", {"name": "server1", "host": "user@1.2.3.4"})
# Appends to events.jsonl

# Sync via git
os.system('cd ~/.local/share/aios && git add -A && git commit -m sync && git push')

# Device B: Pull and rebuild
os.system('cd ~/.local/share/aios && git pull')

def replay_events():
    conn.execute("DELETE FROM ssh")  # Wipe everything!
    for event in open("events.jsonl"):
        e = json.loads(event)
        if e["op"] == "ssh.add":
            conn.execute("INSERT INTO ssh VALUES (?,?,?)",
                        (e["d"]["name"], e["d"]["host"], e["d"]["pw"]))
    # Rebuilds entire table from scratch every time
```

---

## Recommendation for aio

| Current | Improvement | Effort |
|---------|-------------|--------|
| Full replay | Track `lastEventId`, only apply new events | Low |
| Git transport | HTTP POST to simple server (or keep git) | Medium |
| Manual merge | Use CR-SQLite for auto CRDT merge | Low |
| No push | Webhook or poll interval | Medium |

**Minimum viable fix (30 lines):**
```python
def replay_events_incremental():
    last_id = db.get("_last_event_id") or ""
    for line in open("events.jsonl"):
        e = json.loads(line)
        if e["id"] <= last_id: continue  # Skip already-applied
        apply_single_event(e)
        db.set("_last_event_id", e["id"])
```
