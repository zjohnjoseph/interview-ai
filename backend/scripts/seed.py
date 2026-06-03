"""
Seed the database with 50 realistic technical interview questions.

Usage:
    docker compose run --rm api python -m scripts.seed

Idempotent: exits without changes if the questions table is non-empty.
"""
import asyncio

from sqlalchemy import func, select

from app.database import async_session
from app.models.database_models import Question

QUESTIONS: list[dict[str, str]] = [
    # ── Python (10) ──────────────────────────────────────────────────────────

    {
        "text": "What is the difference between a list and a tuple in Python?",
        "domain": "python",
        "difficulty": "easy",
        "reference_answer": (
            "Lists are mutable sequences (elements can be added, removed, or changed) while "
            "tuples are immutable (fixed after creation). Lists use square brackets [], tuples "
            "use parentheses (). Tuples are generally faster to iterate and can be used as "
            "dictionary keys or set members because they are hashable (assuming all elements "
            "are also hashable). Lists are preferred when the collection needs to change; "
            "tuples are preferred for fixed-size heterogeneous data like coordinates or "
            "database rows."
        ),
    },
    {
        "text": "Explain Python's GIL (Global Interpreter Lock). What problem does it solve and what does it prevent?",
        "domain": "python",
        "difficulty": "easy",
        "reference_answer": (
            "The GIL is a mutex that allows only one thread to execute Python bytecode at a "
            "time within a single CPython process. It solves the problem of thread-safe memory "
            "management in CPython's reference-counting garbage collector — without it, two "
            "threads could simultaneously modify an object's reference count, causing "
            "corruption. The downside is that CPU-bound multi-threaded programs cannot "
            "achieve true parallelism in CPython. I/O-bound threads release the GIL while "
            "waiting, so threading still provides concurrency benefits for I/O workloads. "
            "For CPU-bound parallelism, use multiprocessing or async/await instead."
        ),
    },
    {
        "text": "What are Python decorators and how do they work?",
        "domain": "python",
        "difficulty": "easy",
        "reference_answer": (
            "A decorator is a callable that takes a function as an argument and returns a "
            "replacement function. The @syntax is syntactic sugar: @decorator above def f() "
            "is equivalent to f = decorator(f). Decorators are used for cross-cutting concerns "
            "like logging, authentication, caching, and timing. functools.wraps should be used "
            "inside the wrapper to preserve the original function's __name__, __doc__, and "
            "other attributes. Decorators can also accept arguments by adding another layer "
            "of wrapping (a decorator factory)."
        ),
    },
    {
        "text": (
            "Explain the difference between `__init__` and `__new__` in Python. "
            "When would you use `__new__`?"
        ),
        "domain": "python",
        "difficulty": "medium",
        "reference_answer": (
            "__new__ is a static method that creates and returns a new instance of the class; "
            "it receives the class as its first argument. __init__ initializes the already-"
            "created instance; it receives self. __new__ is called before __init__. You use "
            "__new__ when subclassing immutable types (str, int, tuple) because you can't "
            "change the value after creation in __init__, or when implementing the Singleton "
            "pattern by returning an existing instance instead of creating a new one. In "
            "normal class hierarchies, overriding __new__ is rare."
        ),
    },
    {
        "text": "What are Python generators and how do they differ from regular functions?",
        "domain": "python",
        "difficulty": "medium",
        "reference_answer": (
            "A generator is a function that uses yield instead of return. Calling a generator "
            "function returns a generator object without executing any code. Each call to "
            "next() runs the function body until the next yield, pauses, and returns the "
            "yielded value. The function's local state is preserved between calls. Generators "
            "are lazy — they produce values one at a time rather than building the entire "
            "sequence in memory. This makes them ideal for infinite sequences, large file "
            "processing, and pipeline-style data transformations. Generator expressions "
            "(parentheses instead of brackets) provide a concise syntax."
        ),
    },
    {
        "text": "Explain Python's `asyncio` event loop. How does async/await differ from threading?",
        "domain": "python",
        "difficulty": "medium",
        "reference_answer": (
            "The asyncio event loop is a single-threaded scheduler that manages coroutines. "
            "When a coroutine hits an await expression on an I/O operation, control returns "
            "to the event loop, which can run other coroutines while waiting. Unlike threads, "
            "there is no context switching overhead and no risk of race conditions on shared "
            "state within a single thread. async/await is cooperative multitasking — each "
            "coroutine voluntarily yields control. Threading is preemptive — the OS can "
            "interrupt at any point. asyncio is better for high-concurrency I/O (thousands of "
            "connections); threading is simpler for moderate concurrency and works with "
            "blocking libraries that cannot be made async."
        ),
    },
    {
        "text": "What is Python's `__slots__` and when would you use it?",
        "domain": "python",
        "difficulty": "medium",
        "reference_answer": (
            "__slots__ is a class variable that replaces the per-instance __dict__ with a "
            "fixed set of descriptors. Declaring __slots__ = ('x', 'y') prevents instances "
            "from having any attributes other than x and y. Benefits: reduced memory usage "
            "(no __dict__ per instance — important when creating millions of small objects), "
            "faster attribute access (fixed offsets vs. dict lookup), and accidental attribute "
            "creation is caught at runtime. Drawbacks: cannot add new attributes dynamically, "
            "no default pickling support without __getstate__/__setstate__, and inheritance "
            "with non-slotted classes reintroduces __dict__."
        ),
    },
    {
        "text": "How does Python's garbage collector handle reference cycles?",
        "domain": "python",
        "difficulty": "hard",
        "reference_answer": (
            "CPython's primary memory management is reference counting: objects are freed when "
            "their reference count drops to zero. This fails for reference cycles (A → B → A) "
            "because neither object's count reaches zero. The cyclic garbage collector "
            "(gc module) supplements reference counting by periodically scanning objects in "
            "three generations. It traces through object graphs looking for groups of objects "
            "whose combined internal references account for all their external references, "
            "identifying them as unreachable cycles. Weak references (weakref module) are a "
            "design pattern to break cycles — they don't increment reference counts and become "
            "None when the referent is collected. __del__ on objects in cycles can delay or "
            "prevent collection in older Python versions."
        ),
    },
    {
        "text": (
            "Explain the descriptor protocol in Python. How do `property`, `classmethod`, "
            "and `staticmethod` use it?"
        ),
        "domain": "python",
        "difficulty": "hard",
        "reference_answer": (
            "A descriptor is any object that defines __get__, __set__, or __delete__. When an "
            "attribute lookup on a class or instance finds a descriptor in the class hierarchy, "
            "Python calls the descriptor's methods instead of returning the object directly. "
            "Data descriptors (define __set__) take priority over instance __dict__; non-data "
            "descriptors (only __get__) don't. property is a data descriptor that wraps getter/"
            "setter/deleter functions — __get__ calls the getter, __set__ calls the setter. "
            "classmethod's __get__ binds the class (not the instance) to the wrapped function. "
            "staticmethod's __get__ returns the raw function with no binding. The descriptor "
            "protocol is also the foundation of ORM field types and form fields in frameworks."
        ),
    },
    {
        "text": (
            "What is the difference between `deepcopy` and `copy` in Python? "
            "Describe a case where using the wrong one causes a bug."
        ),
        "domain": "python",
        "difficulty": "hard",
        "reference_answer": (
            "copy.copy() creates a shallow copy: a new object whose contents are references to "
            "the same objects as the original. copy.deepcopy() recursively copies all nested "
            "objects, producing a fully independent clone. A shallow copy of a list of lists "
            "creates a new outer list but the inner lists are shared — mutating an inner list "
            "through the copy also mutates the original. Example bug: default mutable "
            "arguments (def f(lst=[])) are a related issue; using shallow copy to clone a "
            "'template' dict that contains nested mutable values will cause shared state bugs "
            "when those nested values are modified. deepcopy is slower and may fail on objects "
            "with circular references unless __deepcopy__ is defined."
        ),
    },

    # ── Data Structures (9) ───────────────────────────────────────────────────

    {
        "text": "What is the time complexity of searching in a hash table? When does it degrade?",
        "domain": "data_structures",
        "difficulty": "easy",
        "reference_answer": (
            "Average-case O(1) for search, insert, and delete. Degrades to O(n) worst-case "
            "when many keys hash to the same bucket (hash collision), causing all operations "
            "on that bucket to become a linear scan. Good hash functions distribute keys "
            "uniformly to minimize collisions. Load factor (n/m, items/buckets) determines "
            "collision probability — rehashing (doubling bucket count) keeps load factor low. "
            "Python's dict uses open addressing with a compact table, maintaining O(1) average "
            "by resizing at two-thirds capacity."
        ),
    },
    {
        "text": "Explain the difference between a stack and a queue, and give one real-world use case for each.",
        "domain": "data_structures",
        "difficulty": "easy",
        "reference_answer": (
            "A stack is LIFO (Last In, First Out): push and pop operate on the same end. "
            "Use case: function call stacks, undo/redo in editors, depth-first search. "
            "A queue is FIFO (First In, First Out): enqueue at the back, dequeue from the "
            "front. Use case: task queues, print spoolers, breadth-first search, message "
            "brokers like Kafka. In Python, collections.deque supports O(1) appendleft/pop "
            "for queues; a list used as a queue has O(n) pop(0). The queue module provides "
            "thread-safe Queue and LifoQueue implementations."
        ),
    },
    {
        "text": "What is a linked list? Compare it to an array in terms of time complexity for common operations.",
        "domain": "data_structures",
        "difficulty": "easy",
        "reference_answer": (
            "A linked list stores elements as nodes where each node holds a value and a "
            "pointer to the next node. Arrays store elements in contiguous memory. "
            "Access by index: O(1) for arrays (direct offset calculation), O(n) for linked "
            "lists (must traverse from head). Insert/delete at the beginning: O(1) for linked "
            "lists (update one pointer), O(n) for arrays (shift all elements). Insert/delete "
            "in the middle: O(n) for both (need to find the position). Memory: arrays have "
            "better cache locality; linked lists have per-node pointer overhead. Doubly-linked "
            "lists add a prev pointer enabling O(1) deletion given the node."
        ),
    },
    {
        "text": "Explain how a binary search tree (BST) works. What is its average vs. worst-case time complexity?",
        "domain": "data_structures",
        "difficulty": "medium",
        "reference_answer": (
            "A BST is a binary tree where every node's left subtree contains only values less "
            "than the node's value, and the right subtree contains only greater values. This "
            "invariant allows binary search during lookup: at each node, go left if the target "
            "is smaller, right if larger. Average-case O(log n) for search, insert, and delete "
            "when the tree is balanced (height ≈ log n). Worst-case O(n) when the tree "
            "degenerates into a linked list (e.g., inserting already-sorted data). "
            "Self-balancing trees (AVL, Red-Black) maintain O(log n) worst-case by rotating "
            "nodes after insertions and deletions. Python's sortedcontainers.SortedList uses "
            "a B-tree variant."
        ),
    },
    {
        "text": "What is a heap and how does it support priority queue operations efficiently?",
        "domain": "data_structures",
        "difficulty": "medium",
        "reference_answer": (
            "A heap is a complete binary tree satisfying the heap property: in a min-heap, "
            "every parent is ≤ its children (max-heap: ≥). Stored as an array using index "
            "arithmetic (left child = 2i+1, right = 2i+2, parent = (i-1)//2). peek-min is "
            "O(1) (the root). insert is O(log n): append to the array, then sift up by "
            "swapping with parent while heap property is violated. extract-min is O(log n): "
            "swap root with last element, shrink array, sift down. Python's heapq module "
            "provides a min-heap on lists. For custom priority, use (priority, item) tuples. "
            "Heapify (converting an arbitrary array to a heap) is O(n), not O(n log n)."
        ),
    },
    {
        "text": "Describe the difference between DFS and BFS graph traversal. When would you choose each?",
        "domain": "data_structures",
        "difficulty": "medium",
        "reference_answer": (
            "Depth-First Search (DFS) explores as far as possible along each branch before "
            "backtracking. Uses a stack (or recursion). Memory: O(depth of graph). BFS "
            "explores all neighbors at the current depth before moving deeper. Uses a queue. "
            "Memory: O(width of graph at the widest level). Choose BFS when: finding shortest "
            "path in unweighted graphs, finding nodes within k hops, level-order tree "
            "traversal. Choose DFS when: detecting cycles, topological sort, finding strongly "
            "connected components, exploring all paths, maze solving. DFS is simpler to "
            "implement recursively; BFS is guaranteed to find the shortest path."
        ),
    },
    {
        "text": (
            "Explain how a hash map handles collisions using open addressing vs. "
            "separate chaining."
        ),
        "domain": "data_structures",
        "difficulty": "hard",
        "reference_answer": (
            "Separate chaining: each bucket holds a linked list (or other structure) of all "
            "keys that hash to that bucket. Simple to implement, handles high load factors, "
            "but has pointer overhead and poor cache locality. Open addressing: all entries "
            "stored in the table itself. On collision, probe for the next open slot using a "
            "sequence (linear probing: +1, quadratic: +i², double hashing: second hash "
            "function). Pros: better cache locality (data in contiguous memory), no pointer "
            "overhead. Cons: deletion is tricky (must use tombstones or backward shift), "
            "clustering degrades performance at high load factors. Python's dict uses open "
            "addressing with pseudo-random probing."
        ),
    },
    {
        "text": "What is a trie (prefix tree) and what problems is it particularly well-suited for?",
        "domain": "data_structures",
        "difficulty": "hard",
        "reference_answer": (
            "A trie stores strings character by character in a tree where each node represents "
            "a character. The root represents the empty string; each path from root to a "
            "marked node represents a complete word. Insert and lookup are O(L) where L is "
            "the string length, independent of the number of stored strings. Space: O(A × L × N) "
            "where A is alphabet size — can be compressed with Patricia/radix tries. "
            "Ideal for: autocomplete (enumerate all words with a given prefix in O(L + k)), "
            "spell checking, IP routing tables (longest-prefix match), dictionary word "
            "validation, and counting distinct substrings. Alternatives: hash sets for exact "
            "match only; suffix arrays/trees for substring search."
        ),
    },
    {
        "text": (
            "Explain consistent hashing. Why is it used in distributed systems "
            "rather than a simple modulo hash?"
        ),
        "domain": "data_structures",
        "difficulty": "hard",
        "reference_answer": (
            "Simple modulo hashing (key % N) assigns each key to one of N buckets. Adding or "
            "removing a server changes N, requiring almost all keys to be remapped — a "
            "massive reshuffling unsuitable for caches or distributed stores. Consistent "
            "hashing maps both servers and keys onto a ring (0 to 2³²). A key is assigned to "
            "the first server clockwise from its position. Adding a server only affects keys "
            "between the new server and its predecessor — on average 1/N of all keys. "
            "Virtual nodes (multiple points per server) improve load balance. Used in "
            "DynamoDB, Cassandra, Redis Cluster, and CDN cache routing. Provides O(1) key "
            "lookup and minimal redistribution on topology changes."
        ),
    },

    # ── SQL (8) ───────────────────────────────────────────────────────────────

    {
        "text": "What is the difference between INNER JOIN, LEFT JOIN, and FULL OUTER JOIN?",
        "domain": "sql",
        "difficulty": "easy",
        "reference_answer": (
            "INNER JOIN returns only rows that have matching values in both tables. LEFT JOIN "
            "returns all rows from the left table plus matching rows from the right table; "
            "non-matching right-side columns are NULL. RIGHT JOIN is the mirror of LEFT JOIN. "
            "FULL OUTER JOIN returns all rows from both tables, with NULLs on either side "
            "where there is no match. Use INNER JOIN when you only care about matches; "
            "LEFT JOIN when you want all left-table rows regardless of whether they match "
            "(e.g., users and their optional orders); FULL OUTER JOIN when you want to find "
            "rows in either table that have no counterpart in the other."
        ),
    },
    {
        "text": "What is a database index? What are the trade-offs of adding indexes?",
        "domain": "sql",
        "difficulty": "easy",
        "reference_answer": (
            "An index is a separate data structure (usually a B-tree) that maps column values "
            "to row locations, allowing the database to find rows without scanning the entire "
            "table. SELECT performance improves dramatically for indexed columns. Trade-offs: "
            "additional disk space (indexes can be as large as the table), slower writes "
            "(INSERT, UPDATE, DELETE must also update all indexes on modified columns), "
            "query planner must choose the right index (statistics must be current). Best for: "
            "columns in WHERE, JOIN ON, and ORDER BY clauses, high-cardinality columns "
            "(many distinct values). Avoid: indexing every column, low-cardinality columns "
            "like boolean flags (full scan is often faster)."
        ),
    },
    {
        "text": "Explain what a SQL transaction is and what ACID properties guarantee.",
        "domain": "sql",
        "difficulty": "easy",
        "reference_answer": (
            "A transaction is a sequence of SQL statements treated as a single unit of work. "
            "ACID guarantees: Atomicity — all statements succeed or all are rolled back, no "
            "partial execution. Consistency — the database moves from one valid state to "
            "another, maintaining all constraints and rules. Isolation — concurrent "
            "transactions behave as if they executed serially; one transaction's intermediate "
            "state is not visible to others (level varies: read uncommitted, read committed, "
            "repeatable read, serializable). Durability — committed transactions survive "
            "crashes (written to persistent storage via WAL). In PostgreSQL, every statement "
            "outside an explicit BEGIN is its own implicit transaction."
        ),
    },
    {
        "text": "What is the N+1 query problem and how do you fix it?",
        "domain": "sql",
        "difficulty": "medium",
        "reference_answer": (
            "The N+1 problem occurs when fetching a list of N parent records and then issuing "
            "one query per record to fetch its related children — producing N+1 total queries "
            "instead of the optimal 2 (or 1 with a JOIN). Example: fetching 100 users and "
            "then querying each user's orders individually sends 101 queries. Fixes: "
            "(1) JOIN — fetch users and orders in one query, grouping in application code. "
            "(2) SELECT ... WHERE user_id IN (...) — batch-fetch all related records in one "
            "query. In ORMs: SQLAlchemy's selectinload/joinedload, Django's select_related "
            "(JOIN) and prefetch_related (IN query). The correct choice depends on "
            "cardinality — joinedload produces duplicate rows for one-to-many; selectinload "
            "is cleaner for large result sets."
        ),
    },
    {
        "text": "Explain window functions in SQL. Give an example using ROW_NUMBER().",
        "domain": "sql",
        "difficulty": "medium",
        "reference_answer": (
            "Window functions perform calculations across a set of rows related to the current "
            "row without collapsing them like GROUP BY does. Syntax: FUNCTION() OVER "
            "(PARTITION BY col ORDER BY col ROWS/RANGE BETWEEN ...). Common functions: "
            "ROW_NUMBER(), RANK(), DENSE_RANK(), LAG(), LEAD(), SUM() OVER(), AVG() OVER(). "
            "Example: SELECT id, department, salary, ROW_NUMBER() OVER (PARTITION BY "
            "department ORDER BY salary DESC) AS rank FROM employees — assigns a rank within "
            "each department. Use case: top-N per group (filter WHERE rank <= 3), running "
            "totals, moving averages, detecting gaps in sequences. Evaluated after WHERE and "
            "GROUP BY but before ORDER BY and LIMIT."
        ),
    },
    {
        "text": "What is query plan analysis and how would you use EXPLAIN ANALYZE to optimize a slow query?",
        "domain": "sql",
        "difficulty": "medium",
        "reference_answer": (
            "EXPLAIN shows the query planner's execution strategy without running the query. "
            "EXPLAIN ANALYZE actually executes it and shows real row counts and timing. "
            "Key things to look for: Seq Scan on large tables (missing index), Hash Join vs. "
            "Nested Loop (bad for large inputs without index), high 'rows removed by filter' "
            "(index not selective enough), and estimated vs. actual row counts (stale "
            "statistics — run ANALYZE). Optimization steps: add an index on the WHERE/JOIN "
            "column, run ANALYZE to update statistics, rewrite subqueries as JOINs, avoid "
            "functions on indexed columns in WHERE (prevents index use), use partial indexes "
            "for filtered queries. EXPLAIN (FORMAT JSON, BUFFERS true, ANALYZE) gives the "
            "most detail in PostgreSQL."
        ),
    },
    {
        "text": "Explain database normalization. What are 1NF, 2NF, and 3NF?",
        "domain": "sql",
        "difficulty": "hard",
        "reference_answer": (
            "Normalization organizes a database to reduce data redundancy and improve integrity. "
            "1NF (First Normal Form): each column holds atomic (indivisible) values; no "
            "repeating groups; each row is unique. 2NF: in 1NF and every non-key attribute is "
            "fully functionally dependent on the entire primary key (no partial dependencies — "
            "relevant when the key is composite). 3NF: in 2NF and no transitive dependencies "
            "(non-key attributes depend only on the key, not on other non-key attributes). "
            "BCNF (Boyce-Codd) is a stricter form of 3NF. Denormalization trades redundancy "
            "for read performance (fewer JOINs). In practice, most OLTP schemas aim for 3NF; "
            "data warehouses often use star schemas (denormalized) for query performance."
        ),
    },
    {
        "text": "What are PostgreSQL's isolation levels and what anomalies does each prevent?",
        "domain": "sql",
        "difficulty": "hard",
        "reference_answer": (
            "SQL defines four isolation levels with corresponding anomalies: "
            "Read Uncommitted — no protection (dirty reads, non-repeatable reads, phantoms). "
            "PostgreSQL doesn't implement this; it uses Read Committed instead. "
            "Read Committed (default in PG) — prevents dirty reads; a transaction sees only "
            "committed data, but the same query may return different rows if re-executed "
            "within the transaction (non-repeatable reads). "
            "Repeatable Read — prevents dirty and non-repeatable reads; a transaction sees a "
            "consistent snapshot from its start. PostgreSQL's implementation also prevents "
            "phantom reads. "
            "Serializable — prevents all anomalies; transactions behave as if executed one "
            "at a time. PostgreSQL uses SSI (Serializable Snapshot Isolation), which detects "
            "and aborts conflicting transaction cycles. Higher isolation = fewer anomalies "
            "but more lock contention or abort rate."
        ),
    },

    # ── System Design (8) ─────────────────────────────────────────────────────

    {
        "text": "What is horizontal vs. vertical scaling? When would you choose each?",
        "domain": "system_design",
        "difficulty": "easy",
        "reference_answer": (
            "Vertical scaling (scale up) adds more resources to an existing machine — more "
            "CPU, RAM, or faster disks. Simple, no code changes required, but has a hard "
            "ceiling (single machine limits) and creates a single point of failure. "
            "Horizontal scaling (scale out) adds more machines and distributes load across "
            "them. Requires stateless services or shared state (database, cache), load "
            "balancers, and distributed coordination. No theoretical ceiling. Choose vertical "
            "first for simplicity and when the workload fits one machine; move to horizontal "
            "when approaching hardware limits, when you need fault tolerance and redundancy, "
            "or when traffic spikes require elastic capacity."
        ),
    },
    {
        "text": "What is a CDN (Content Delivery Network) and how does it improve performance?",
        "domain": "system_design",
        "difficulty": "easy",
        "reference_answer": (
            "A CDN is a geographically distributed network of edge servers that cache and "
            "serve static content (images, CSS, JS, videos) from locations close to users. "
            "Reduces latency by serving from the nearest edge node instead of the origin "
            "server. Reduces origin load by caching responses (cache-hit rate depends on "
            "TTL and content diversity). Provides DDoS protection via large distributed "
            "capacity. CDNs like Cloudflare, CloudFront, and Fastly also offer TLS "
            "termination, HTTP/2 and HTTP/3 support, WAF rules, and image optimization. "
            "Dynamic content can be partially cached (vary by headers) or served via CDN "
            "routing with reduced hop count to origin."
        ),
    },
    {
        "text": "Design the high-level architecture of a URL shortener like bit.ly.",
        "domain": "system_design",
        "difficulty": "medium",
        "reference_answer": (
            "Key components: (1) Write service: receive long URL, generate a short code "
            "(base62 encoding of a counter or hash of the URL), store long↔short mapping in "
            "a DB (e.g., {short_code, original_url, created_at, user_id}). (2) Read service: "
            "receive short code, look up in cache (Redis) first, then DB if cache miss, "
            "return 301 (permanent, cacheable) or 302 (temporary, analytics-friendly) "
            "redirect. (3) Database: PostgreSQL or Cassandra for the mapping; Redis as a "
            "read-through cache with TTL. (4) Analytics: async queue (Kafka) for click "
            "events, processed by a stream processor into time-series storage. "
            "Scaling: reads >> writes; cache hit rate ~99% for popular URLs. Counter "
            "generation: distributed (Snowflake ID) to avoid hot-spot on a single DB row."
        ),
    },
    {
        "text": "Explain the CAP theorem and how it applies to database selection.",
        "domain": "system_design",
        "difficulty": "medium",
        "reference_answer": (
            "The CAP theorem states that a distributed system can guarantee at most two of "
            "three properties simultaneously: Consistency (all nodes see the same data at "
            "the same time), Availability (every request receives a response, not necessarily "
            "the latest data), and Partition Tolerance (the system continues operating despite "
            "network partitions). Since network partitions are unavoidable in distributed "
            "systems, the real trade-off is CP vs. AP. CP systems (HBase, ZooKeeper, "
            "etcd) sacrifice availability during a partition to maintain consistency. "
            "AP systems (Cassandra, DynamoDB, CouchDB) remain available but may return "
            "stale data. PACELC extends this to also consider latency vs. consistency "
            "trade-offs during normal operation."
        ),
    },
    {
        "text": "What is a message queue? Explain how Kafka's architecture enables high throughput.",
        "domain": "system_design",
        "difficulty": "medium",
        "reference_answer": (
            "A message queue decouples producers and consumers: producers publish messages "
            "without knowing who consumes them, and consumers process at their own pace. "
            "Kafka's high throughput comes from several design choices: (1) Log-structured "
            "storage — messages are appended to an immutable, ordered log; sequential disk "
            "writes are an order of magnitude faster than random writes. (2) Partitioning — "
            "each topic is split into partitions distributed across brokers; consumers read "
            "from assigned partitions in parallel. (3) Consumer offsets — consumers track "
            "their own position, so the broker doesn't need to track delivery state. "
            "(4) Batching and compression — producers and brokers batch messages; consumers "
            "read in batches. (5) Zero-copy file transfer (sendfile) to reduce CPU overhead."
        ),
    },
    {
        "text": "Design a rate limiter for an API. What algorithms can be used and what are the trade-offs?",
        "domain": "system_design",
        "difficulty": "hard",
        "reference_answer": (
            "Common algorithms: (1) Fixed Window — count requests in discrete time windows "
            "(e.g., per minute). Simple, but allows 2× burst at window boundaries. "
            "(2) Sliding Window Log — store a timestamp per request; reject if count in "
            "[now-60s, now] exceeds limit. Accurate, but O(requests) memory per user. "
            "(3) Sliding Window Counter — weighted blend of current and previous window "
            "counts. O(1) memory, good approximation. (4) Token Bucket — tokens added at a "
            "fixed rate, consumed per request; allows short bursts up to bucket capacity. "
            "(5) Leaky Bucket — requests processed at a constant rate; excess queued or "
            "dropped; smooths traffic. For distributed systems, use Redis INCR + EXPIRE "
            "(fixed window), or Redis sorted sets (sliding log). Lua scripts ensure atomicity. "
            "Propagation delay between nodes means distributed rate limiting is approximate."
        ),
    },
    {
        "text": (
            "Design a distributed job scheduler that needs to run millions of tasks reliably "
            "with at-least-once semantics."
        ),
        "domain": "system_design",
        "difficulty": "hard",
        "reference_answer": (
            "Components: (1) Job store — database (PostgreSQL) holding job definitions "
            "(id, scheduled_at, status, payload, retries). (2) Scheduler — polls for due "
            "jobs (SELECT FOR UPDATE SKIP LOCKED to avoid contention between scheduler "
            "replicas); enqueues into a work queue. (3) Work queue — Kafka or SQS for "
            "durable delivery; partitioned by job type for parallelism. (4) Workers — consume "
            "from queue, execute job, mark complete or increment retry count. At-least-once: "
            "workers ACK only after success; on failure the message is redelivered. "
            "Idempotency keys in job payloads protect against double execution. (5) Dead "
            "letter queue for jobs that exceed max retries. (6) Exactly-once is harder — "
            "requires transactional outbox or two-phase commit with the job store. "
            "Cron scheduling: store next_run_at, recalculate after each execution."
        ),
    },
    {
        "text": "How would you design a system to handle 10 million concurrent WebSocket connections?",
        "domain": "system_design",
        "difficulty": "hard",
        "reference_answer": (
            "Key constraints: each WebSocket is a persistent TCP connection; a single server "
            "can handle ~100k connections with tuned OS limits (ulimit, tcp_tw_reuse, "
            "SO_REUSEPORT). For 10M: (1) Gateway tier — many lightweight connection servers "
            "(e.g., nginx, Envoy, or custom async servers in Go/Erlang) maintain connections; "
            "these machines are I/O-bound not CPU-bound, so maximize file descriptors and use "
            "event-driven I/O. (2) Routing — each gateway maps connection_id to its node; "
            "publish routing info to Redis or a service registry. (3) Message delivery — "
            "when a backend wants to push to a user, look up their gateway node and forward "
            "via an internal pub/sub (Redis pub/sub, Kafka, or direct gRPC). (4) Stateless "
            "backends — business logic runs separately from connection state. (5) Heartbeats "
            "and reconnect — clients reconnect with exponential backoff on disconnect; "
            "gateways heartbeat to detect dead connections."
        ),
    },

    # ── Machine Learning (8) ──────────────────────────────────────────────────

    {
        "text": "What is the difference between supervised and unsupervised learning? Give one example of each.",
        "domain": "ml",
        "difficulty": "easy",
        "reference_answer": (
            "Supervised learning trains on labeled data (input-output pairs) to learn a "
            "mapping from inputs to outputs. Example: training a model on house features "
            "(size, location) and prices to predict the price of new houses (regression), "
            "or classifying emails as spam/not-spam given labeled examples. "
            "Unsupervised learning finds structure in unlabeled data. Example: clustering "
            "customer purchase histories with k-means to discover segments without predefined "
            "categories, or using PCA to reduce high-dimensional data to a lower-dimensional "
            "representation. Semi-supervised learning uses a small labeled set and a large "
            "unlabeled set. Self-supervised learning generates labels from the data itself "
            "(e.g., predicting masked tokens in BERT)."
        ),
    },
    {
        "text": "What is overfitting and what are the main techniques to prevent it?",
        "domain": "ml",
        "difficulty": "easy",
        "reference_answer": (
            "Overfitting occurs when a model memorizes training data instead of learning "
            "generalizable patterns — training loss is low but validation/test loss is high. "
            "Prevention techniques: (1) More training data — reduces the model's ability to "
            "memorize. (2) Regularization — L1 (Lasso) adds absolute weight penalty, promoting "
            "sparsity; L2 (Ridge) adds squared weight penalty, shrinking all weights. "
            "(3) Dropout — randomly zeros activations during training, preventing co-adaptation. "
            "(4) Early stopping — stop training when validation loss stops improving. "
            "(5) Cross-validation — use k-fold CV to tune hyperparameters without leaking "
            "test data. (6) Reduce model complexity — fewer layers, parameters, or features. "
            "(7) Data augmentation — artificially expand training set with transforms."
        ),
    },
    {
        "text": "Explain the attention mechanism in transformers. Why did it replace RNNs for NLP?",
        "domain": "ml",
        "difficulty": "medium",
        "reference_answer": (
            "Attention computes a weighted sum of value vectors, where weights come from the "
            "compatibility between a query and a set of keys: Attention(Q,K,V) = "
            "softmax(QK^T / sqrt(d_k)) V. Multi-head attention runs this in parallel with "
            "different learned projections, capturing different types of relationships. "
            "RNNs process sequences step-by-step, requiring O(n) sequential operations — "
            "gradient vanishing over long sequences makes capturing long-range dependencies "
            "hard. Transformers compute attention over the full sequence in parallel (O(n²) "
            "compute but highly parallelizable on GPUs), capturing any pairwise relationship "
            "in one step. This enables training on much larger datasets and scales better. "
            "Self-attention allows each token to directly attend to every other token, "
            "solving the long-range dependency problem."
        ),
    },
    {
        "text": "What is gradient descent? Explain the difference between batch, mini-batch, and stochastic variants.",
        "domain": "ml",
        "difficulty": "medium",
        "reference_answer": (
            "Gradient descent minimizes a loss function by iteratively updating parameters "
            "in the direction opposite to the gradient: θ = θ - α∇L(θ). "
            "Batch GD: computes the gradient over the entire training set per update. "
            "Advantages: accurate gradient; smooth convergence. Disadvantages: very slow for "
            "large datasets; cannot update until all data is processed. "
            "Stochastic GD (SGD): computes gradient on a single random example per update. "
            "Fast updates, noisy gradient — high variance in parameter updates, can escape "
            "local minima. Mini-batch GD: computes gradient on a small batch (32–512 "
            "examples). Best of both: vectorized GPU computation, lower variance than SGD, "
            "more frequent updates than batch. In practice, 'SGD' usually means mini-batch. "
            "Variants like Adam, RMSprop, and AdaGrad adapt the learning rate per parameter."
        ),
    },
    {
        "text": "What is the bias-variance trade-off in machine learning?",
        "domain": "ml",
        "difficulty": "medium",
        "reference_answer": (
            "Prediction error = bias² + variance + irreducible noise. "
            "Bias is the error from incorrect assumptions — a high-bias model is too simple "
            "and underfits (misses patterns in the data). Variance is sensitivity to small "
            "fluctuations in the training set — a high-variance model overfits (memorizes "
            "noise). Increasing model complexity reduces bias but increases variance. "
            "The trade-off: a simple linear model has high bias/low variance; a deep neural "
            "network has low bias/high variance without regularization. The goal is to find "
            "the right model complexity where total error is minimized. Ensemble methods "
            "(bagging reduces variance, boosting reduces bias) and modern overparameterized "
            "models (double descent) have complicated this classical view."
        ),
    },
    {
        "text": "Explain how RAG (Retrieval-Augmented Generation) works and why it outperforms fine-tuning for knowledge-intensive tasks.",
        "domain": "ml",
        "difficulty": "hard",
        "reference_answer": (
            "RAG combines a retriever with a generator LLM. At query time: (1) embed the "
            "query using a dense encoder, (2) retrieve the top-k most similar document chunks "
            "from a vector store (e.g., pgvector, Pinecone, Weaviate), (3) prepend the "
            "retrieved context to the prompt, (4) generate an answer conditioned on both the "
            "query and the retrieved context. Advantages over fine-tuning: (1) Knowledge is "
            "updated by modifying the vector store without retraining. (2) Sources can be "
            "cited (grounding). (3) Much cheaper — no GPU training required. (4) Handles "
            "long-tail knowledge that wasn't in training data. Fine-tuning is better for "
            "changing the model's style, format, or behavior; RAG is better for factual "
            "knowledge retrieval. Hybrid approaches fine-tune the retriever or reader on "
            "domain-specific data."
        ),
    },
    {
        "text": "What are the key differences between BERT and GPT architectures? When would you use each?",
        "domain": "ml",
        "difficulty": "hard",
        "reference_answer": (
            "BERT uses a bidirectional encoder — each token attends to all other tokens in "
            "both directions simultaneously. Trained with masked language modeling (predict "
            "masked tokens) and next-sentence prediction. Output: contextualized embeddings "
            "for every input token. Best for: classification, NER, question answering, "
            "semantic similarity — tasks where understanding the full context is critical. "
            "GPT uses a unidirectional decoder — each token only attends to previous tokens "
            "(causal masking). Trained with next-token prediction (language modeling). "
            "Output: generates the next token autoregressively. Best for: text generation, "
            "summarization, translation, code generation, conversational AI. "
            "Encoder-decoder models (T5, BART) combine both: encoder processes input, "
            "decoder generates output — well-suited for translation and abstractive summarization."
        ),
    },
    {
        "text": "Explain how you would detect and mitigate data leakage in a machine learning pipeline.",
        "domain": "ml",
        "difficulty": "hard",
        "reference_answer": (
            "Data leakage occurs when information from outside the training set influences "
            "the model, producing over-optimistic evaluation metrics that don't hold on real "
            "data. Types: (1) Target leakage — features that include information about the "
            "target that wouldn't be available at prediction time (e.g., a 'discharge date' "
            "field when predicting hospital readmission). (2) Train-test contamination — "
            "preprocessing (scaling, imputation, feature selection) fit on the full dataset "
            "before splitting. Detection: suspiciously high validation accuracy, feature "
            "importance showing unexpected predictors, temporal data not respecting time "
            "order. Mitigations: use sklearn Pipelines so transformers are fit only on "
            "training folds; time-based splits for sequential data; carefully audit feature "
            "definitions for future-looking information; hold out a completely separate "
            "final test set not used for any model selection decisions."
        ),
    },

    # ── APIs (7) ──────────────────────────────────────────────────────────────

    {
        "text": "What is REST? List the core constraints that define a RESTful API.",
        "domain": "apis",
        "difficulty": "easy",
        "reference_answer": (
            "REST (Representational State Transfer) is an architectural style for distributed "
            "hypermedia systems, defined by six constraints: (1) Client-server — UI and data "
            "storage are separated. (2) Stateless — each request contains all information "
            "needed to process it; session state is held on the client. (3) Cacheable — "
            "responses must define themselves as cacheable or not. (4) Uniform interface — "
            "resource identification via URIs, manipulation through representations, "
            "self-descriptive messages, HATEOAS. (5) Layered system — clients don't know "
            "if they're talking to the origin server or an intermediary. (6) Code on demand "
            "(optional) — servers can extend client functionality by sending executable code. "
            "Statelessness is the most important constraint for scalability — any server can "
            "handle any request without shared session state."
        ),
    },
    {
        "text": "What is the difference between authentication and authorization? Give examples of each.",
        "domain": "apis",
        "difficulty": "easy",
        "reference_answer": (
            "Authentication verifies identity — who are you? Examples: username/password "
            "login, OAuth2 tokens, API keys, biometrics, mTLS client certificates. "
            "Authorization determines permissions — what are you allowed to do? Examples: "
            "role-based access control (RBAC) where admin can delete users but viewers "
            "cannot, attribute-based access control (ABAC) where access depends on resource "
            "attributes and environment, scopes in OAuth2 (read:posts vs. write:posts). "
            "In a typical API flow: the client authenticates (presents JWT), the server "
            "verifies the token signature (authentication), then checks the user's role or "
            "permissions against the requested resource and action (authorization). "
            "Common mistake: returning 401 Unauthorized when 403 Forbidden is correct "
            "(the user is authenticated but lacks permission)."
        ),
    },
    {
        "text": "What is JWT (JSON Web Token)? Explain its structure and security considerations.",
        "domain": "apis",
        "difficulty": "medium",
        "reference_answer": (
            "A JWT is a compact, URL-safe token with three base64url-encoded parts separated "
            "by dots: header.payload.signature. Header: algorithm (HS256, RS256) and token "
            "type. Payload: claims — registered (iss, sub, exp, iat), public, and private. "
            "Signature: HMAC or RSA signature over header.payload, verifiable without a "
            "database lookup. Security considerations: (1) Always verify the signature and "
            "check exp. (2) Use HTTPS — JWTs in headers can be intercepted. (3) Store in "
            "httpOnly cookies (not localStorage) to prevent XSS theft. (4) Keep payloads "
            "small — they're encoded, not encrypted; sensitive data shouldn't be in the "
            "payload (use JWE for encryption). (5) Short expiry + refresh tokens reduces "
            "the window if a token is stolen. (6) RS256 (asymmetric) is preferred for "
            "multi-service architectures — services verify with the public key, only the "
            "auth server holds the private key."
        ),
    },
    {
        "text": "Compare REST, GraphQL, and gRPC. When would you choose each?",
        "domain": "apis",
        "difficulty": "medium",
        "reference_answer": (
            "REST: resource-oriented URLs, HTTP verbs, JSON. Simple, widely understood, "
            "great for public APIs and CRUD services. Cons: over-fetching (getting more "
            "fields than needed) and under-fetching (multiple round trips for related data). "
            "GraphQL: single endpoint, clients specify exactly what fields they need in a "
            "query. Eliminates over/under-fetching. Best for complex frontends with diverse "
            "data needs (mobile vs. web). Cons: caching is harder (POST queries), N+1 "
            "problem on the server (requires DataLoader), learning curve. "
            "gRPC: HTTP/2 + Protocol Buffers (binary, compact). Strongly typed contracts "
            "(proto files), streaming support, generated client/server code. Best for "
            "internal microservice communication where performance matters. Cons: binary "
            "format is not human-readable, not browser-native. "
            "Choose REST for public APIs; GraphQL for complex frontend data needs; "
            "gRPC for high-throughput internal services."
        ),
    },
    {
        "text": "What are idempotency and safety in HTTP methods? Why does this matter for API design?",
        "domain": "apis",
        "difficulty": "medium",
        "reference_answer": (
            "A safe method has no side effects on the server — GET and HEAD are safe "
            "(read-only). An idempotent method can be called multiple times with the same "
            "effect as one call — GET, HEAD, PUT, DELETE, and OPTIONS are idempotent. "
            "POST is neither safe nor idempotent (creates a new resource each time). "
            "PATCH is idempotent only if defined carefully. Why it matters: (1) Clients and "
            "proxies can retry idempotent requests automatically on network failure without "
            "risk of duplicate side effects. (2) GET requests can be cached safely. "
            "(3) PUT should be used for full-resource replacement (idempotent); PATCH for "
            "partial updates. Design implication: use idempotency keys on POST endpoints "
            "(e.g., payment APIs) so clients can safely retry without double-charging."
        ),
    },
    {
        "text": "How do you version a REST API? Compare URL versioning, header versioning, and content negotiation.",
        "domain": "apis",
        "difficulty": "hard",
        "reference_answer": (
            "API versioning strategies: (1) URL versioning (/api/v1/users, /api/v2/users) — "
            "explicit, easy to test in a browser, easy to route in reverse proxies. Downside: "
            "pollutes URLs with infrastructure concerns; breaking changes require major "
            "version bumps with long deprecation periods. (2) Request header versioning "
            "(API-Version: 2) — clean URLs, but harder to test manually and requires "
            "clients to set headers explicitly. (3) Content negotiation (Accept: "
            "application/vnd.company.v2+json) — standards-compliant, but complex to "
            "implement and debug. In practice, URL versioning (v1, v2) is most common "
            "due to simplicity. Best practices: version only on breaking changes; maintain "
            "backwards compatibility as long as feasible; sunset old versions with "
            "Deprecation and Sunset headers; document migration guides."
        ),
    },
    {
        "text": "Design an API rate limiting and quota system for a SaaS product with multiple pricing tiers.",
        "domain": "apis",
        "difficulty": "hard",
        "reference_answer": (
            "Components: (1) Tier definitions — store tier config (free: 100 req/day, "
            "pro: 10k req/day, enterprise: unlimited) in a config service or database. "
            "(2) Identity — extract API key or JWT from request; look up the associated "
            "account and tier. (3) Rate limiting — sliding window counter in Redis per "
            "account: INCR key, EXPIRE if new, reject if count > limit. Use Lua script "
            "for atomicity. (4) Quota — daily/monthly aggregate in Redis or a time-series "
            "DB; reset at billing period boundaries. (5) Response headers — include "
            "X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset on every response "
            "so clients can self-throttle. (6) Graceful degradation — return 429 with "
            "Retry-After header; provide a webhook or email alert when approaching limits. "
            "(7) Burst allowance — token bucket allows short bursts without penalizing "
            "bursty-but-low-average clients. (8) Audit log — record every rate limit "
            "event for billing verification and abuse analysis."
        ),
    },
]


async def seed() -> None:
    async with async_session() as db:
        count = (await db.execute(select(func.count(Question.id)))).scalar_one()
        if count > 0:
            print(f"Already seeded ({count} questions present). Skipping.")
            return

        for q in QUESTIONS:
            db.add(Question(**q))
        await db.commit()

    domain_counts: dict[str, int] = {}
    for q in QUESTIONS:
        domain_counts[q["domain"]] = domain_counts.get(q["domain"], 0) + 1

    print(f"Seeded {len(QUESTIONS)} questions across {len(domain_counts)} domains:")
    for domain, count in sorted(domain_counts.items()):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    asyncio.run(seed())
