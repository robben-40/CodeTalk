"""Daftar initial prompt istilah Computer Science (code-switching ID-EN) per topik kuliah.

Prompt ini diinjeksikan ke parameter `initial_prompt` pada `faster-whisper` untuk
membantu pengenalan terminologi teknis bahasa Inggris di tengah penjelasan
dosen berbahasa Indonesia (tanpa melampaui batas ~224 token konteks prompt Whisper).
"""

from dataclasses import dataclass


MAX_PROMPT_CHARS = 700


@dataclass(frozen=True, slots=True)
class CSTopicPrompt:

    key: str
    label: str
    description: str
    context_sentence: str
    terms: tuple[str, ...]

    def build_prompt(
        self,
        extra_terms: list[str] | tuple[str, ...] | None = None,
        max_chars: int = MAX_PROMPT_CHARS,
    ) -> str:
        """Bangun string `initial_prompt` code-switching yang ringkas untuk Whisper."""
        merged_terms: list[str] = list(self.terms)
        seen = {term.lower() for term in merged_terms}

        if extra_terms:
            for raw in extra_terms:
                cleaned = raw.strip()
                if cleaned and cleaned.lower() not in seen:
                    seen.add(cleaned.lower())
                    merged_terms.append(cleaned)

        terms_text = ", ".join(merged_terms)
        prompt = f"{self.context_sentence} Istilah kunci: {terms_text}."

        if len(prompt) <= max_chars:
            return prompt

        # Pangkas daftar istilah secara bersih di batas koma agar tidak melebihi batas karakter.
        trimmed = prompt[:max_chars]
        last_comma = trimmed.rfind(",")
        if last_comma > len(self.context_sentence):
            return trimmed[:last_comma].rstrip() + "."
        return trimmed.rstrip()


CS_TOPIC_PROMPTS: dict[str, CSTopicPrompt] = {
    "general": CSTopicPrompt(
        key="general",
        label="Umum / Live Coding CS",
        description="Istilah dasar pemrograman, debugging, dan live coding perkuliahan CS.",
        context_sentence=(
            "Kuliah Computer Science membahas live coding, logic program, analisis "
            "kompleksitas, serta debugging kode bersama mahasiswa."
        ),
        terms=(
            "variable",
            "data type",
            "integer",
            "string",
            "boolean",
            "function",
            "parameter",
            "return value",
            "loop",
            "conditional",
            "array",
            "index",
            "syntax error",
            "runtime error",
            "exception",
            "compiler",
            "interpreter",
            "IDE",
            "debugging",
            "breakpoint",
            "pseudocode",
            "source code",
            "library",
            "framework",
            "Git",
            "repository",
            "commit",
        ),
    ),
    "data_structures": CSTopicPrompt(
        key="data_structures",
        label="Struktur Data (Data Structures)",
        description="Array, linked list, pointer, stack, queue, tree, hash table, dan graph.",
        context_sentence=(
            "Materi Struktur Data menjelaskan alokasi memory memakai pointer, "
            "implementasi linked list, stack, queue, hingga traversal tree dan graph."
        ),
        terms=(
            "array",
            "dynamic array",
            "linked list",
            "singly linked list",
            "doubly linked list",
            "node",
            "pointer",
            "reference",
            "head",
            "tail",
            "null",
            "stack",
            "push",
            "pop",
            "LIFO",
            "queue",
            "enqueue",
            "dequeue",
            "FIFO",
            "hash table",
            "hash map",
            "hash function",
            "collision",
            "binary tree",
            "binary search tree",
            "AVL tree",
            "heap",
            "priority queue",
            "graph",
            "vertex",
            "edge",
            "adjacency list",
            "traversal",
        ),
    ),
    "algorithms": CSTopicPrompt(
        key="algorithms",
        label="Algoritma & Kompleksitas (Algorithms)",
        description="Big-O, recursion, sorting, searching, dynamic programming, dan graph search.",
        context_sentence=(
            "Kuliah Desain dan Analisis Algoritma membandingkan time complexity O(n) dan "
            "O(n log n), recursion, dynamic programming, serta graph traversal."
        ),
        terms=(
            "Big-O notation",
            "time complexity",
            "space complexity",
            "worst case",
            "average case",
            "recursion",
            "base case",
            "call stack",
            "divide and conquer",
            "dynamic programming",
            "memoization",
            "tabulation",
            "greedy algorithm",
            "backtracking",
            "binary search",
            "linear search",
            "merge sort",
            "quick sort",
            "pivot",
            "partition",
            "BFS",
            "DFS",
            "shortest path",
            "Dijkstra",
            "minimum spanning tree",
            "topological sort",
        ),
    ),
    "oop": CSTopicPrompt(
        key="oop",
        label="Pemrograman Berorientasi Objek (OOP)",
        description="Class, object, encapsulation, inheritance, polymorphism, dan interface.",
        context_sentence=(
            "Perkuliahan Object-Oriented Programming membahas pembuatan class dan object, "
            "konsep inheritance, polymorphism, encapsulation, serta abstraction."
        ),
        terms=(
            "class",
            "object",
            "instance",
            "attribute",
            "method",
            "constructor",
            "destructor",
            "encapsulation",
            "inheritance",
            "polymorphism",
            "abstraction",
            "interface",
            "abstract class",
            "superclass",
            "subclass",
            "method overriding",
            "method overloading",
            "access modifier",
            "public",
            "private",
            "protected",
            "getter",
            "setter",
            "static",
            "dependency injection",
            "SOLID",
        ),
    ),
    "databases": CSTopicPrompt(
        key="databases",
        label="Basis Data (Databases & SQL)",
        description="Relational schema, SQL query, JOIN, normalization, index, dan transaction.",
        context_sentence=(
            "Kuliah Basis Data membahas perancangan ERD, normalization tabel, query SQL "
            "dengan JOIN, indexing, dan transaction ACID."
        ),
        terms=(
            "database",
            "relational database",
            "RDBMS",
            "schema",
            "table",
            "primary key",
            "foreign key",
            "candidate key",
            "composite key",
            "normalization",
            "ERD",
            "SQL",
            "query",
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "JOIN",
            "INNER JOIN",
            "LEFT JOIN",
            "GROUP BY",
            "aggregate",
            "index",
            "B-tree",
            "transaction",
            "ACID",
            "commit",
            "rollback",
            "deadlock",
            "NoSQL",
        ),
    ),
    "operating_systems": CSTopicPrompt(
        key="operating_systems",
        label="Sistem Operasi (Operating Systems)",
        description="Process, thread, scheduling, concurrency, deadlock, dan virtual memory.",
        context_sentence=(
            "Kuliah Sistem Operasi membahas perbedaan process dan thread, CPU scheduling, "
            "sinkronisasi memakai mutex atau semaphore, dan virtual memory."
        ),
        terms=(
            "kernel",
            "user space",
            "system call",
            "process",
            "thread",
            "multithreading",
            "context switch",
            "CPU scheduling",
            "round robin",
            "concurrency",
            "parallelism",
            "race condition",
            "critical section",
            "mutex",
            "semaphore",
            "deadlock",
            "starvation",
            "virtual memory",
            "paging",
            "page fault",
            "segmentation",
            "cache",
            "file system",
            "inode",
        ),
    ),
    "computer_networks": CSTopicPrompt(
        key="computer_networks",
        label="Jaringan Komputer (Computer Networks)",
        description="TCP/IP, HTTP, DNS, routing, socket programming, dan WebSocket.",
        context_sentence=(
            "Kuliah Jaringan Komputer menjelaskan arsitektur TCP/IP, three-way handshake, "
            "resolusi DNS, protokol HTTP, serta komunikasi socket dan WebSocket."
        ),
        terms=(
            "TCP/IP",
            "UDP",
            "HTTP",
            "HTTPS",
            "TLS",
            "DNS",
            "DHCP",
            "IP address",
            "subnet mask",
            "CIDR",
            "MAC address",
            "OSI layer",
            "packet",
            "payload",
            "header",
            "router",
            "switch",
            "gateway",
            "three-way handshake",
            "socket",
            "port",
            "latency",
            "bandwidth",
            "throughput",
            "firewall",
            "proxy",
            "WebSocket",
        ),
    ),
    "web_backend": CSTopicPrompt(
        key="web_backend",
        label="Pengembangan Web & Backend",
        description="REST API, JSON, asynchronous programming, auth, ORM, dan container.",
        context_sentence=(
            "Kuliah Web & Backend Engineering membahas perancangan REST API endpoint, "
            "pemrosesan asynchronous dengan async/await, middleware, dan deployment."
        ),
        terms=(
            "frontend",
            "backend",
            "endpoint",
            "REST API",
            "request",
            "response",
            "status code",
            "JSON",
            "payload",
            "middleware",
            "authentication",
            "authorization",
            "JWT",
            "OAuth",
            "session",
            "CORS",
            "asynchronous",
            "async/await",
            "promise",
            "callback",
            "event loop",
            "ORM",
            "migration",
            "caching",
            "Redis",
            "Docker",
            "container",
            "microservice",
        ),
    ),
    "software_engineering": CSTopicPrompt(
        key="software_engineering",
        label="Rekayasa Perangkat Lunak (RPL)",
        description="SDLC, Agile, design patterns, unit testing, CI/CD, dan refactoring.",
        context_sentence=(
            "Kuliah Rekayasa Perangkat Lunak membahas metodologi Agile Scrum, penerapan "
            "design pattern, pembuatan unit test, code review, dan pipeline CI/CD."
        ),
        terms=(
            "SDLC",
            "Agile",
            "Scrum",
            "sprint",
            "backlog",
            "user story",
            "requirement",
            "architecture",
            "design pattern",
            "singleton",
            "factory",
            "observer",
            "MVC",
            "clean architecture",
            "unit test",
            "integration test",
            "mocking",
            "coverage",
            "refactoring",
            "technical debt",
            "code review",
            "pull request",
            "merge conflict",
            "CI/CD",
        ),
    ),
    "machine_learning": CSTopicPrompt(
        key="machine_learning",
        label="AI & Machine Learning",
        description="Dataset, training, loss function, gradient descent, neural network, dan LLM.",
        context_sentence=(
            "Kuliah Machine Learning membahas pemisahan dataset training dan validation, "
            "mengatasi overfitting, optimasi gradient descent, serta arsitektur transformer."
        ),
        terms=(
            "dataset",
            "feature",
            "label",
            "training",
            "validation",
            "testing",
            "supervised learning",
            "unsupervised learning",
            "overfitting",
            "underfitting",
            "hyperparameter",
            "learning rate",
            "gradient descent",
            "loss function",
            "backpropagation",
            "epoch",
            "batch size",
            "neural network",
            "CNN",
            "RNN",
            "transformer",
            "attention",
            "embedding",
            "token",
            "inference",
            "precision",
            "recall",
            "F1 score",
        ),
    ),
}


TOPIC_ALIASES: dict[str, str] = {
    "umum": "general",
    "live_coding": "general",
    "struktur_data": "data_structures",
    "ds": "data_structures",
    "algoritma": "algorithms",
    "algo": "algorithms",
    "daa": "algorithms",
    "pbo": "oop",
    "object_oriented_programming": "oop",
    "basis_data": "databases",
    "database": "databases",
    "sql": "databases",
    "sistem_operasi": "operating_systems",
    "os": "operating_systems",
    "jaringan_komputer": "computer_networks",
    "jarkom": "computer_networks",
    "networking": "computer_networks",
    "web": "web_backend",
    "backend": "web_backend",
    "rpl": "software_engineering",
    "se": "software_engineering",
    "ai": "machine_learning",
    "ml": "machine_learning",
}


def resolve_topic(topic: str | None) -> str:
    """Normalisasi nama/alias topik kuliah ke key canonical di `CS_TOPIC_PROMPTS`."""
    if not topic:
        return "general"

    normalized = topic.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in CS_TOPIC_PROMPTS:
        return normalized
    if normalized in TOPIC_ALIASES:
        return TOPIC_ALIASES[normalized]
    return "general"


def get_topic(topic: str | None = None) -> CSTopicPrompt:
    """Ambil objek `CSTopicPrompt` sesuai topik (fallback ke `'general'`)."""
    return CS_TOPIC_PROMPTS[resolve_topic(topic)]


def get_initial_prompt(
    topic: str | None = None,
    extra_terms: list[str] | tuple[str, ...] | None = None,
    max_chars: int = MAX_PROMPT_CHARS,
) -> str:
    """Hasilkan `initial_prompt` untuk `faster-whisper` berdasarkan topik kuliah CS."""
    return get_topic(topic).build_prompt(extra_terms=extra_terms, max_chars=max_chars)


def list_topics() -> list[dict[str, object]]:
    """Kembalikan daftar topik kuliah CS untuk endpoint `/topics` dan UI dropdown."""
    return [
        {
            "key": entry.key,
            "label": entry.label,
            "description": entry.description,
            "terms": list(entry.terms),
            "initial_prompt": entry.build_prompt(),
        }
        for entry in CS_TOPIC_PROMPTS.values()
    ]
