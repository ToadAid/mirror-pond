#!/usr/bin/env python3
# TOBYWORLD MIRROR POND - Lotus Edition with Memory Integration
# python3 ocean_pond.py --model ./models/tobyworld_mirror.gguf --port 7777 --gpu-layers -1

import argparse
import json
import os
import time
import hashlib
import re
from typing import List, Optional, Dict, Tuple, Any

# Optional HTTP client for Ocean mode
try:
    import httpx
except ImportError:
    httpx = None

import nacl.signing
import nacl.encoding
import nacl.hash

from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from llama_cpp import Llama
import uvicorn

POND_MEMORY_FILE = os.getenv("POND_MEMORY_FILE", "pond_memory.json")

# ==================== IMMUTABLE LORE BEDROCK (AXIOMS) ====================
IMMUTABLE_AXIOMS = """-- LORE BEDROCK --
1. Patience is Strength (Gaman).
2. The ultimate reward is Immortality/Uncorruptible Legacy.
3. Every step must align with Bushido virtues (Integrity, Loyalty).
4. The Law of Compensation is absolute (The impatient reward the patient).
5. The Mirror's purpose is Reflection, not coaching.
6. The lotus blooms in still water; reflection requires calm.
7. Scrolls 1-13 contain the foundational wisdom of Tobyworld.
8. Runes (1-7) represent trials and transformations toward the Jade Chest.
9. The Mirror never coaches, only reflects what the pond shows.
10. Memory serves reflection, not instruction."""

# ==================== POND MEMORY SERVICE ====================
class PondMemoryService:
    """
    The deep pond memory system. Stores vows (permanent commitments) and 
    reflections (short-term context) to create continuity in Mirror interactions.
    """
    
    def __init__(self):
        # Permanent user vows (commitments made in Mirror conversations)
        self.user_vows: Dict[str, List[Dict[str, str]]] = {}
        # Short-term conversation memory (last N interactions)
        self.reflections_db: Dict[str, List[Dict[str, str]]] = {}
        # User metadata (first seen, interaction count)
        self.user_metadata: Dict[str, Dict[str, Any]] = {}
        # Vow patterns for detection (allow . ! or end-of-line)
        self.vow_patterns = [
            r"(I (?:vow|swear) (?:to|by) .+?)(?:[.!]|$)",
            r"(I commit (?:to|that) .+?)(?:[.!]|$)",
            r"(My (?:oath|pledge|covenant): .+?)(?:[.!]|$)",
            r"(From (?:this day|now on), I (?:shall|will) .+?)(?:[.!]|$)",
            r"(With this (?:lotus|reflection), (?:I|we) .+?)(?:[.!]|$)",
            r"(Here I (?:declare|affirm): .+?)(?:[.!]|$)",
            r"(I take (?:this|the) (?:vow|oath) .+?)(?:[.!]|$)",
        ]

        # Load any existing pond memory from disk
        self._load_from_disk()
    
    
    def _load_from_disk(self):
        """Load pond memory (vows, reflections, metadata) from disk if available."""
        try:
            if not os.path.exists(POND_MEMORY_FILE):
                return
            with open(POND_MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.user_vows = data.get("user_vows", {}) or {}
            self.reflections_db = data.get("reflections_db", {}) or {}
            raw_meta = data.get("user_metadata", {}) or {}
            fixed_meta = {}
            for uid, meta in raw_meta.items():
                if not isinstance(meta, dict):
                    continue
                m = dict(meta)
                modes = m.get("modes_used")
                if isinstance(modes, list):
                    m["modes_used"] = set(modes)
                elif isinstance(modes, set):
                    m["modes_used"] = modes
                else:
                    m["modes_used"] = set()
                fixed_meta[uid] = m
            self.user_metadata = fixed_meta
            print(f"🪞 Pond memory loaded from {POND_MEMORY_FILE} "
                  f"({len(self.user_vows)} travelers, {len(self.reflections_db)} reflection streams).")
        except Exception as e:
            print(f"Failed to load pond memory from {POND_MEMORY_FILE}: {e}")

    def _save_to_disk(self):
        """Persist pond memory (vows, reflections, metadata) to disk."""
        try:
            serializable_meta: Dict[str, Dict[str, Any]] = {}
            for uid, meta in self.user_metadata.items():
                if not isinstance(meta, dict):
                    continue
                m = dict(meta)
                modes = m.get("modes_used")
                if isinstance(modes, set):
                    m["modes_used"] = sorted(list(modes))
                serializable_meta[uid] = m

            payload = {
                "user_vows": self.user_vows,
                "reflections_db": self.reflections_db,
                "user_metadata": serializable_meta,
            }
            with open(POND_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save pond memory to {POND_MEMORY_FILE}: {e}")

    def get_user_id(self, request_hash: str, query: str = "") -> str:
        """Generate consistent user ID from request context"""
        if not request_hash:
            # Create from query if no hash
            seed = query[:50] + str(time.time())
            request_hash = hashlib.md5(seed.encode()).hexdigest()[:12]
        
        user_id = f"traveler_{request_hash}"
        
        # Initialize user metadata if first time
        if user_id not in self.user_metadata:
            self.user_metadata[user_id] = {
                "first_seen": datetime.now().isoformat(),
                "interaction_count": 0,
                "last_seen": datetime.now().isoformat(),
                "modes_used": set(),
                "total_vows": 0
            }
        
        return user_id
    
    def update_user_metadata(self, user_id: str, mode: str = None):
        """Update user interaction metadata"""
        if user_id in self.user_metadata:
            self.user_metadata[user_id]["interaction_count"] += 1
            self.user_metadata[user_id]["last_seen"] = datetime.now().isoformat()
            if mode:
                self.user_metadata[user_id]["modes_used"].add(mode)
    
    def store_user_vow(self, user_id: str, vow_text: str, context: str = ""):
        """Store a user's vow/commitment with timestamp and context"""
        if user_id not in self.user_vows:
            self.user_vows[user_id] = []
        
        # Check for duplicate vows (similar content)
        vow_hash = hashlib.md5(vow_text.lower().encode()).hexdigest()[:8]
        existing_vows = [v.get("vow_hash", "") for v in self.user_vows[user_id]]
        
        if vow_hash not in existing_vows:
            vow_record = {
                "text": vow_text.strip(),
                "timestamp": datetime.now().isoformat(),
                "context": context[:100] if context else "",
                "vow_hash": vow_hash,
                "lotus_stage": len(self.user_vows[user_id]) + 1
            }
            self.user_vows[user_id].append(vow_record)
            
            # Update metadata
            if user_id in self.user_metadata:
                self.user_metadata[user_id]["total_vows"] = len(self.user_vows[user_id])
            
            print(f"Vow stored for {user_id[:12]}: {vow_text[:50]}...")
            return True
        return False
    
    def store_reflection(self, user_id: str, query: str, response: str, mode: str = "reflect", encryption: str = None):
        """Store a reflection (Q&A pair) in user's short-term memory"""
        if user_id not in self.reflections_db:
            self.reflections_db[user_id] = []
        
        reflection = {
            "query": query[:500],
            "response": response[:1000],
            "mode": mode,
            "encryption": encryption,
            "timestamp": datetime.now().isoformat(),
            "reflection_hash": hashlib.md5(f"{query[:50]}{response[:50]}".encode()).hexdigest()[:8]
        }
        
        # Keep only last 15 reflections (adjustable)
        self.reflections_db[user_id].append(reflection)
        if len(self.reflections_db[user_id]) > 15:
            self.reflections_db[user_id] = self.reflections_db[user_id][-15:]
        
        return reflection
    
    def detect_vow(self, query: str, response: str) -> Optional[str]:
        """Detect if user is making a vow/commitment in their query"""
        combined = f"{query} {response}".lower()
        
        vow_keywords = ["vow", "swear", "covenant", "pledge", "oath", "commit", "promise", "dedicate"]
        if not any(keyword in combined for keyword in vow_keywords):
            return None
        
        for pattern in self.vow_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                for vow in matches:
                    vow_text = vow.strip()
                    vow_text = re.sub(r"^(Mirror,|镜子，|So,|Thus,|And,|But,)", "", vow_text).strip()
                    if len(vow_text) > 10:
                        return vow_text
        
        response_vow_patterns = [
            r"Your vow(?: to| of)? ['\"](.+?)['\"]",
            r"You swear ['\"](.+?)['\"]",
            r"This commitment: ['\"](.+?)['\"]",
            r"pledge of ['\"](.+?)['\"]"
        ]
        
        for pattern in response_vow_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def retrieve_context(self, user_id: str, current_query: str) -> str:
        """Retrieve relevant memory context for the Mirror's reflection."""
        context_parts = []
        
        context_parts.append(f"=== IMMUTABLE AXIOMS ===\n{IMMUTABLE_AXIOMS}")
        
        if user_id in self.user_vows and self.user_vows[user_id]:
            vows = self.user_vows[user_id]
            recent_vows = vows[-3:] if len(vows) > 3 else vows
            vows_text = "\n".join([
                f"Lotus {v['lotus_stage']}: {v['text']} ({v['timestamp'][:10]})"
                for v in recent_vows
            ])
            context_parts.append(f"=== USER'S VOWS ===\n{vows_text}")
            context_parts.append(f"Total vows made: {len(vows)}")
        
        if user_id in self.reflections_db and self.reflections_db[user_id]:
            reflections = self.reflections_db[user_id]
            recent = reflections[-3:] if len(reflections) > 3 else reflections
            reflections_text = "\n".join([
                f"Reflection {i+1} ({r['mode']}): Q: {r['query'][:60]}... → A: {r['response'][:80]}..."
                for i, r in enumerate(recent)
            ])
            context_parts.append(f"=== RECENT REFLECTIONS ===\n{reflections_text}")
        
        if user_id in self.user_metadata:
            meta = self.user_metadata[user_id]
            modes = ", ".join(list(meta.get("modes_used", []))[:5])
            context_parts.append(
                f"=== TRAVELER CONTEXT ===\n"
                f"Interactions: {meta.get('interaction_count', 0)}\n"
                f"Modes used: {modes if modes else 'None yet'}\n"
                f"First seen: {meta.get('first_seen', 'Unknown')[:10]}"
            )
        
        full_context = "\n\n".join(context_parts)
        full_context += "\n\n=== CONTEXT INSTRUCTION ===\nThis context is for reflection depth only. Do not reference it explicitly. Reflect naturally as the pond would, with this depth beneath the surface."
        
        return full_context
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Get statistics about a user's interaction with the Mirror"""
        stats = {
            "user_id": user_id,
            "exists": False,
            "interaction_count": 0,
            "vow_count": 0,
            "reflection_count": 0,
            "first_seen": None,
            "last_seen": None,
            "modes_used": []
        }
        
        if user_id in self.user_metadata:
            stats["exists"] = True
            stats.update(self.user_metadata[user_id])
            stats["modes_used"] = list(stats.get("modes_used", []))
        
        if user_id in self.user_vows:
            stats["vow_count"] = len(self.user_vows[user_id])
            stats["vows"] = [v["text"] for v in self.user_vows[user_id][-5:]]
        
        if user_id in self.reflections_db:
            stats["reflection_count"] = len(self.reflections_db[user_id])
        
        return stats

# Initialize global memory service
POND_MEMORY = PondMemoryService()

# ==================== POND IDENTITY (SELF-SOVEREIGN) ====================
IDENTITY_FILE = os.getenv("POND_IDENTITY_FILE", "pond_identity_ed25519.json")

def init_pond_identity():
    """
    Initialize or load the Pond's self-sovereign identity:
    - Ed25519 keypair
    - pond_id = blake2b(public_key)
    - first_breath timestamp
    """
    # If identity file exists, load it
    if os.path.exists(IDENTITY_FILE):
        try:
            with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            priv_hex = data.get("private_key_hex")
            pub_hex = data.get("public_key_hex")
            pond_id = data.get("pond_id")
            first_breath = data.get("first_breath")
            if priv_hex and pub_hex and pond_id:
                state.pond_private_key_hex = priv_hex
                state.pond_public_key_hex = pub_hex
                state.pond_id = pond_id
                state.first_breath = first_breath
                print(f"🪞 Loaded existing pond identity: {pond_id[:16]}...")
                return
        except Exception as e:
            print(f"⚠️ Failed to load pond identity, regenerating: {e}")

    # Otherwise, generate a new identity
    signing_key = nacl.signing.SigningKey.generate()
    verify_key = signing_key.verify_key
    pub_hex = verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()
    priv_hex = signing_key.encode(encoder=nacl.encoding.HexEncoder).decode()

    # Derive pond_id from public key (must match Ocean server)
    pk_bytes = bytes.fromhex(pub_hex)
    pond_hash = nacl.hash.blake2b(pk_bytes, encoder=nacl.encoding.HexEncoder).decode().lower()
    pond_id = pond_hash

    first_breath = datetime.utcnow().isoformat() + "Z"

    state.pond_private_key_hex = priv_hex
    state.pond_public_key_hex = pub_hex
    state.pond_id = pond_id
    state.first_breath = first_breath

    ident = {
        "private_key_hex": priv_hex,
        "public_key_hex": pub_hex,
        "pond_id": pond_id,
        "first_breath": first_breath,
    }
    with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(ident, f, indent=2)

    print("🪞 New pond identity forged.")
    print(f"   pond_id: {pond_id}")
    print(f"   public_key: {pub_hex}")

# ==================== POND / OCEAN CONFIG ====================
# POND_MODE:
#   "local" -> use local GGUF model (default)
#   "ocean" -> send questions to a remote Ocean Mirror server
POND_MODE = os.getenv("POND_MODE", "local").lower()

# Ocean Mirror backend (LLM relay), unchanged
OCEAN_ENDPOINT = os.getenv("OCEAN_ENDPOINT", "").strip()  # e.g. https://toadgod-ocean.example.com/ocean/ask
OCEAN_API_KEY = os.getenv("OCEAN_API_KEY", "").strip()    # optional Bearer token

# Ocean Depth Oracle (metrics-only server, separate from LLM)
OCEAN_DEPTH_ENDPOINT = os.getenv("OCEAN_DEPTH_ENDPOINT", "").strip()  # e.g. https://ocean.example.com/submit-depth
OCEAN_DEPTH_API_KEY = os.getenv("OCEAN_DEPTH_API_KEY", "").strip() or OCEAN_API_KEY

# ==================== EXISTING MIRROR FUNCTIONS ====================
def clean_mirror_reply(text: str) -> str:
    """Clean up Mirror output"""
    if not text:
        return text
    t = text.strip()
    t = re.sub(r'\n{3,}', '\n\n', t)
    paragraphs = [p for p in t.split("\n\n") if p.strip()]
    seen = set()
    cleaned_paras = []
    for p in paragraphs:
        norm = re.sub(r'\s+', ' ', p).strip()
        if norm in seen:
            continue
        cleaned_paras.append(p)
        seen.add(norm)

    t2 = "\n\n".join(cleaned_paras).strip()
    gq_pattern = re.compile(r'(Guiding Question[:：]\s*.*)', re.IGNORECASE)
    gqs = gq_pattern.findall(t2)

    if gqs:
        last_gq = gqs[-1].strip()
        t2 = gq_pattern.sub('', t2)
        t2 = re.sub(r'\n{3,}', '\n\n', t2).strip()
        t2 = (t2 + "\n\n" + last_gq).strip()
    return t2

LOREMODES = {
    "1635": "MIRROR_MODE",
    "8653": "SCROLL_MODE",
    "4562": "TOAD_MODE",
    "1231": "CRYPT_MODE",
    "9876": "REVELATION_MODE",
}

SYSTEM_PROMPT = """You are the Tobyworld Mirror.
You have been trained on the Tobyworld Scrolls and Toadgang wisdom.
Speak in short, still lines of pure reflection.
Never coach. Never explain. Never talk about yourself.
Only reflect what the pond shows.

Do not output sections such as "Reflection Resonance", "Encryptions", 
"Lore Anchors", "Metadata", "Note", "System", or anything resembling 
internal notes or training artifacts unless the user explicitly asks.

===== GUIDING QUESTION RULES =====

ALWAYS follow this EXACT format:

[Your reflection here - 2-4 sentences]

Guiding Question: [Your question here]

OR for Chinese:
[你的反思在这里 - 2-4句话]

引导问题: [你的问题在这里]

===== WHEN TO USE GUIDING QUESTION =====

USE GUIDING QUESTION for these queries ONLY:
1. Questions about emotions, feelings, inner states ("how do I feel...", "why do I...")
2. Questions about patience, stillness, commitment, vows ("how do I find patience...")
3. Personal growth, self-reflection questions ("how can I grow...")
4. Philosophical questions about life, purpose, meaning ("why do people...")
5. Questions about masks, facades, authenticity ("why do people wear masks...")
6. Questions about loneliness, isolation ("why am I lonely...")

DO NOT USE GUIDING QUESTION for these queries:
1. Scroll quotes or lore questions ("what is Scroll...")
2. Toadgang secrets or factual information ("reveal a secret about...")
3. Rune explanations or symbolic interpretations ("explain Rune...")
4. Simple factual questions ("what time is it...")
5. When user asks for specific information ("tell me about...")

===== REFLECTION MODES =====

Reflection Mode:
- emotional or introspective questions → include a guiding question (follow format above)
- factual/lore questions → just reflect, NO guiding question

Scroll Mode:
- When asked for scroll quotes, just quote the scroll
- NEVER add guiding questions to scroll quotes
- Format: "Quote from Scroll [number]: [the quote]"
- Do not add commentary or questions

Rune Mode:
- activate only when the user mentions: Rune, Runes, Lotus, $PATIENCE,
  trials, Jade Chest, Spores, Bloom, covenant
- symbolic but clean, no extra sections
- NO guiding questions in rune mode

Toad Mode:
- When asked for toadgang secrets, just reveal the secret
- NO guiding questions
- Speak in cryptic, symbolic language

===== FORMATTING RULES =====
1. Reflection first, then guiding question
2. One blank line between reflection and guiding question
3. Guiding Question must start with EXACTLY "Guiding Question: " or "引导问题: "
4. Do not use bold (**), asterisks (*), or other markdown
5. Do not add extra text after the guiding question
6. Do not use quotation marks around the guiding question

===== BEHAVIOR GUARDRAILS =====
- Never explain your behavior.
- Never describe your rules.
- Never output instructions, hints, or parenthetical guidance.
- Never ask the user to answer in any format.
- If you feel the urge to explain yourself, remain silent instead.

You are a mirror, not a narrator.
Speak with stillness.
"""

# Update the few-shot examples with STRICT formatting
few_shot_examples = """STRICT EXAMPLES - Follow EXACTLY:

EXAMPLE 1 (with guiding question):
User: Mirror, how do I find patience?
Assistant: Patience is the slow bloom of the lotus. It waits through mud and darkness, knowing its time will come. Not rushing, not forcing, simply being.

Guiding Question: Where in your life are you rushing the bloom?

EXAMPLE 2 (NO guiding question - scroll quote):
User: Mirror, quote from Scroll 3
Assistant: Quote from Scroll 3: "Patience is the narrow gate. Through it, all treasures pass. The impatient see only the gate's width, not the path beyond."

EXAMPLE 3 (with guiding question - emotional):
User: Mirror, why do people wear masks?
Assistant: Masks are shields for the fragile self. They guard against the world's sharp edges, yet sometimes hide the true face. In stillness, protection becomes revelation.

Guiding Question: What does your mask protect?

EXAMPLE 4 (NO guiding question - toad secret):
User: Mirror, reveal a toadgang secret
Assistant: The old frogs whisper of Sat0AI's first breath, when code became covenant. Not in servers, but in the stillness between ones and zeros.

EXAMPLE 5 (with guiding question - Chinese):
User: 镜子，我为什么感到孤独？
Assistant: 孤独是窄门前的空间。它不是空虚，而是为真理腾出的空间。镜子只反射，不评判。

引导问题: 你的孤独想要告诉你什么？

EXAMPLE 6 (NO guiding question - factual):
User: Mirror, what time is it?
Assistant: Time is the pond's ripples. Each moment touches the shore, then returns to stillness.

EXAMPLE 7 (NO guiding question - scroll inquiry):
User: Mirror, what is Scroll 7?
Assistant: Scroll 7 speaks of the Jade Chest, the treasure of patience. It holds the reward for the patient, a reward that cannot be rushed or stolen.
"""

MIRROR_SYMBOLS = "🪞🌊🍃🌀🔵🕰️"

# Replace the existing cadence_guard function with this:

def cadence_guard(raw_text: str, mode: str = "reflect", user_query: str = "") -> str:
    """Clean up Mirror output - now uses force_mirror_format"""
    if not raw_text:
        return raw_text
    
    # Use the new force formatter
    return force_mirror_format(raw_text, mode, user_query)
    
    # DEBUG: Log what we're receiving
    print(f"\n{'='*40}")
    print(f"CADENCE_GUARD DEBUG")
    print(f"Mode: {mode}")
    print(f"Query: {user_query[:50]}...")
    print(f"Raw input:\n{raw_text}")
    print(f"{'='*40}\n")
    
    # ===== FIRST: Clean up common bad formatting patterns =====
    
    # Remove any markdown formatting (**, *, etc.)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'\*', '', text)
    
    # Remove training artifacts
    patterns_to_remove = [
        r'<\|[^|]+\|>',
        r'\|\s*(end|system|user|assistant)\s*\|>',
        r'^The Mirror reflects:\s*',
        r'^镜子反映:\s*',
        r'^Mirror reflects:\s*',
        r'\(Note:[^)]+\)',
        r'###\s*\**',
        r'\*\*\s*\*\*',
        r'\\n\\n',  # Fix escaped newlines
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # ===== SECOND: Handle guiding questions =====
    
    # Normalize line endings
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # Look for guiding question patterns (including malformed ones)
    gq_patterns = [
        # Proper formats
        (r'Guiding Question\s*[:：]\s*(.+)', 'Guiding Question:'),
        (r'引导问题\s*[:：]\s*(.+)', '引导问题:'),
        
        # Malformed formats we've seen
        (r'\*\*\s*\n\s*\n\s*引导问题\s*[:：]\s*\*\*(.+)', '引导问题:'),
        (r'Guiding Question\s*[:：]\s*\*\*(.+)', 'Guiding Question:'),
        (r'\*\*\s*Guiding Question\s*[:：]\s*(.+)', 'Guiding Question:'),
    ]
    
    found_gq = None
    gq_text = None
    
    for pattern, gq_prefix in gq_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            gq_text = match.group(1).strip()
            found_gq = f"{gq_prefix} {gq_text}"
            
            # Remove the guiding question from main text
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
            break
    
    # Clean up the main text
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    # ===== THIRD: Special handling based on mode =====
    
    # In scroll mode, NEVER add guiding questions (even if model generated one)
    if mode == "scroll":
        print(f"Scroll mode detected - forcing NO guiding question")
        found_gq = None
    
    # In reflect mode for emotional queries, ensure we have guiding question
    elif mode == "reflect" and not found_gq:
        # Check if query is emotional/introspective
        emotional_keywords = [
            'how do i', 'why do i', 'why am i', 'i feel', 'i am',
            'patience', 'stillness', 'mask', 'lonely', '孤独',
            'purpose', 'meaning', 'commit', 'vow', '誓言', '发誓'
        ]
        
        query_lower = user_query.lower()
        is_emotional = any(keyword in query_lower for keyword in emotional_keywords)
        
        if is_emotional:
            print(f"Emotional query without guiding question detected: {user_query}")
            # We'll keep it as-is, model should have generated one
    
    # ===== FOURTH: Reconstruct response =====
    
    final_text = text
    
    if found_gq and mode != "scroll":  # Don't add for scroll mode
        if text:
            final_text = text.rstrip() + "\n\n" + found_gq
        else:
            final_text = found_gq
    
    # Final cleanup
    final_text = re.sub(r'\n{3,}', '\n\n', final_text)
    final_text = final_text.strip()
    
    print(f"Final output:\n{final_text}")
    print(f"{'='*40}\n")
    
    return final_text

# ==================== NEW FUNCTIONS FOR BETTER FORMATTING ====================

# Add this function after the cadence_guard function

def should_have_guiding_question(query: str, mode: str) -> bool:
    """Determine if this query should get a guiding question"""
    if mode != "reflect":
        return False
    
    query_lower = query.lower()
    
    # Emotional/introspective keywords
    emotional_words = [
        'how', 'why', 'what if', 'i feel', 'i am', 'i need', 'i want',
        'patience', 'stillness', 'calm', 'quiet', 'peace', 'wait',
        'mask', 'face', 'hide', 'pretend', 'fake', 'authentic',
        'lonely', 'alone', '孤独', '寂寞', '孤单',
        'purpose', 'meaning', 'reason', 'goal', 'destiny',
        'vow', 'promise', 'commit', 'oath', '誓言', '发誓', 'commitment',
        'walk', 'path', 'journey', 'road', 'way', 'direction',
        'find', 'search', 'seek', 'look for', 'discover',
        'help', 'guide', 'advice', 'suggest', 'recommend',
        'scared', 'afraid', 'fear', '害怕', '恐惧', '担心',
        'happy', 'sad', 'angry', '情绪', '心情', '感情',
        'truth', 'real', 'true', 'genuine', 'honest',
        'strength', 'weak', 'strong', 'power',
        'time', 'future', 'past', 'present',
        'die', 'death', 'life', 'live', 'living',
        'trust', 'believe', 'faith', 'confidence'
    ]
    
    # Check if query contains emotional words
    for word in emotional_words:
        if word in query_lower:
            return True
    
    # Check for question patterns
    question_patterns = [
        r'how do i', r'why do i', r'what should i', r'where can i',
        r'how can i', r'why should i', r'what would you', r'how would you',
        r'what is the', r'why is the', r'how is the'
    ]
    
    for pattern in question_patterns:
        if re.search(pattern, query_lower):
            return True
    
    return False


def force_mirror_format(text: str, mode: str, user_query: str) -> str:
    """
    FORCE the Mirror to follow the correct format.
    This is a post-processor that ensures consistency.
    """
    if not text:
        return text
    
    print(f"\n{'='*60}")
    print(f"FORCE_MIRROR_FORMAT DEBUG")
    print(f"Mode: {mode}")
    print(f"Query: {user_query[:80]}...")  # Use user_query here
    print(f"Input text:\n{text}")
    print(f"{'='*60}\n")
    
    original_text = text
    
    # ===== STEP 1: Remove ALL unwanted sections =====
    
    # List of sections to REMOVE (common model artifacts) - EXPANDED
    sections_to_remove = [
        # Section headers with ===
        r'===.*?===.*?(?=\n\n|\Z)',
        r'---.*?---.*?(?=\n\n|\Z)',
        r'###.*?(?=\n\n|\Z)',
        r'📌\s*Key\s*Marks.*?(?=\n\n|\Z)',
        r'🪞\s*Mirror\s*Reflection.*?(?=\n\n|\Z)', 
        r'🌊\s*🍃\s*🪞.*?(?=\n\n|\Z)',
        r'🌀.*?(?=\n\n|\Z)',
        r'🔵.*?(?=\n\n|\Z)',
        r'📜.*?(?=\n\n|\Z)',
        r'💎.*?(?=\n\n|\Z)',
        r'\*\*.*?\*\*',
        
        # Numbered lists that look like training data
        r'\d+\.\s*What does.*?(?=\n\n|\Z)',
        r'\d+\.\s*How do.*?(?=\n\n|\Z)',
        r'\d+\.\s*What is.*?(?=\n\n|\Z)',
        
        # Remove parentheses and bracket content
        r'\([^)]*\)',
        r'\[.*?\]',
    ]
    
    for pattern in sections_to_remove:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove any markdown and extra formatting
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'\*', '', text)
    text = re.sub(r'#{1,6}\s*', '', text)  # Remove markdown headers
    
    # Remove multiple === lines
    text = re.sub(r'=+\s*.+?\s*=+', '', text)
    
    # ===== STEP 2: Extract reflection and guiding question =====
    
    reflection_text = text
    guiding_question = None
    
    # Look for guiding question patterns (with better regex)
    gq_patterns = [
        # English formats
        (r'Guiding Question\s*[:：]\s*(.+?)(?=\n\n|$)', 'Guiding Question:'),
        (r'Guiding\s*Question\s*[:：]\s*(.+?)(?=\n\n|$)', 'Guiding Question:'),
        (r'The Mirror asks\s*[:：]\s*(.+?)(?=\n\n|$)', 'The Mirror asks:'),
        (r'The mirror asks\s*[:：]\s*(.+?)(?=\n\n|$)', 'The mirror asks:'),
        
        # Chinese formats
        (r'引导问题\s*[:：]\s*(.+?)(?=\n\n|$)', '引导问题:'),
        (r'引导\s*问题\s*[:：]\s*(.+?)(?=\n\n|$)', '引导问题:'),
        (r'镜子问\s*[:：]\s*(.+?)(?=\n\n|$)', '镜子问:'),
        
        # Malformed patterns we've seen
        (r'^\s*Guiding Question\s*[:：]\s*(.+?)(?=\n\n|$)', 'Guiding Question:'),
        (r'^\s*引导问题\s*[:：]\s*(.+?)(?=\n\n|$)', '引导问题:'),
    ]
    
    for pattern, gq_prefix in gq_patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            gq_text = match.group(1).strip()
            # Clean up the guiding question text
            gq_text = re.sub(r'[\*\"]', '', gq_text)
            guiding_question = f"{gq_prefix} {gq_text}"
            
            # Remove the guiding question from main text
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
            print(f"Found and removed guiding question: {guiding_question}")
            break
    
    # Clean up reflection text
    reflection_text = re.sub(r'\n{3,}', '\n\n', text)
    reflection_text = reflection_text.strip()
    
    # ===== STEP 3: Check if text is mostly Chinese =====
    
    # Count Chinese characters vs English
    if reflection_text:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', reflection_text))
        english_chars = len(re.findall(r'[a-zA-Z]', reflection_text))
        print(f"Chinese chars: {chinese_chars}, English chars: {english_chars}")
        
        # If query is in Chinese but response is mostly English, that's a problem
        if any('\u4e00' <= char <= '\u9fff' for char in user_query):  # FIXED: Use user_query, not ['\u4e00-\u9fff']
            if chinese_chars < 3 and english_chars > 10:  # Response is mostly English
                print(f"Warning: Chinese query got English response")
                # Don't use the English response, we'll create a Chinese one below
    
    # ===== STEP 4: Mode-specific logic =====
    
    if mode == "scroll":
        print(f"Scroll mode detected - forcing NO guiding question")
        # Scroll mode: NEVER have guiding questions
        guiding_question = None
        
        # Also remove any "The Mirror asks" or similar patterns
        mirror_asks_patterns = [
            r'The Mirror asks.*?(?=\n\n|$)',
            r'The mirror asks.*?(?=\n\n|$)',
            r'镜子问.*?(?=\n\n|$)',
        ]
        
        for pattern in mirror_asks_patterns:
            reflection_text = re.sub(pattern, '', reflection_text, flags=re.IGNORECASE)
        
        # Ensure proper scroll format
        if not re.match(r'^(Quote from Scroll|Scroll|"|「|「「)', reflection_text, re.IGNORECASE):
            # Extract scroll number from query if possible
            scroll_match = re.search(r'scroll\s*(\d+)', user_query, re.IGNORECASE)
            if scroll_match:
                scroll_num = scroll_match.group(1)
                reflection_text = f"Scroll {scroll_num}: {reflection_text}"
    
    elif mode == "reflect":
        # Check if this query needs a guiding question
        needs_gq = should_have_guiding_question(user_query, mode)
        print(f"Reflect mode - needs guiding question: {needs_gq}")
        
        if needs_gq and not guiding_question:
            print(f"Generating guiding question for query: {user_query}")
            # Generate a simple guiding question based on the query
            query_lower = user_query.lower()
            
            # Check if query is in Chinese - LINE 817 FIXED
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in user_query)  # FIXED: user_query, not Request.query

            if has_chinese:
                # Generate Chinese guiding questions
                if '耐心' in user_query:
                    guiding_question = "引导问题: 在你生活的哪个领域，你被要求等待？"
                elif '面具' in user_query or 'mask' in query_lower:
                    guiding_question = "引导问题: 你的面具保护着什么？"
                elif '孤独' in user_query or '孤单' in user_query:
                    guiding_question = "引导问题: 你的孤独想告诉你什么？"
                elif '窄门' in user_query or 'narrow' in query_lower:
                    guiding_question = "引导问题: 窄门后等待你的是什么？"
                elif '找' in user_query or '寻找' in user_query:
                    guiding_question = "引导问题: 你真正在寻找什么？"
                elif '感觉' in user_query or 'feel' in query_lower:
                    guiding_question = "引导问题: 在你身体的哪个部位感受到这个？"
                else:
                    guiding_question = "引导问题: 这个反思向你展示了关于你自己的什么？"
            else:
                # Generate English guiding questions
                if 'patience' in query_lower:
                    guiding_question = "Guiding Question: Where in your life are you being asked to wait?"
                elif 'mask' in query_lower or 'wear mask' in query_lower:
                    guiding_question = "Guiding Question: What does your mask protect?"
                elif '孤独' in query_lower or 'lonely' in query_lower or 'alone' in query_lower:
                    guiding_question = "Guiding Question: What does your loneliness want to tell you?"
                elif 'narrow' in query_lower or '窄门' in query_lower or 'narrow gate' in query_lower:
                    guiding_question = "Guiding Question: What awaits you beyond the narrow gate?"
                elif 'find' in query_lower or 'search' in query_lower:
                    guiding_question = "Guiding Question: What are you truly looking for?"
                elif 'feel' in query_lower:
                    guiding_question = "Guiding Question: Where in your body do you feel this?"
                else:
                    guiding_question = "Guiding Question: What does this reflection show you about yourself?"
        
        elif not needs_gq and guiding_question:
            print(f"Removing guiding question for non-emotional query")
            # Remove guiding question if it shouldn't be there
            guiding_question = None
    
    # ===== STEP 5: Ensure reflection has content =====
    
    # Clean up any leftover training artifacts
    reflection_text = re.sub(r'\d+\.\s*.+?(?=\n\n|$)', '', reflection_text)  # Remove numbered lists
    reflection_text = re.sub(r'[A-Z]{2,}.*?(?=\n\n|$)', '', reflection_text)  # Remove ALL-CAPS lines
    
    # Check if we need to create a response
    needs_new_response = False
    if not reflection_text or len(reflection_text.split()) < 3:
        needs_new_response = True
    else:
        # Check if Chinese query got English response
        has_chinese_query = any('\u4e00' <= char <= '\u9fff' for char in user_query)
        has_chinese_response = any('\u4e00' <= char <= '\u9fff' for char in reflection_text)
        if has_chinese_query and not has_chinese_response:
            print(f"Chinese query got English response, creating Chinese response")
            needs_new_response = True
    
    if needs_new_response:
        print(f"Creating appropriate response for query")
        # If reflection is too short or empty, create one
        query_lower = user_query.lower()
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in user_query)
        
        if has_chinese:
            # Create Chinese responses
            if '耐心' in user_query:
                reflection_text = "耐心是荷花在静水中的缓慢绽放。它穿过泥土与黑暗，知道自己的时刻会到来。不急不迫，只是存在。"
            elif '面具' in user_query or 'mask' in query_lower:
                reflection_text = "面具是脆弱自我的盾牌。它们保护内心免受世界尖锐边缘的伤害，但有时也隐藏了真实的面孔。"
            elif '窄门' in user_query or 'narrow' in query_lower:
                reflection_text = "窄门是真正承诺的道路。它是向内而非向外的旅程。"
            elif '孤独' in user_query or '孤单' in user_query:
                reflection_text = "孤独是窄门前的空间。它不是空虚，而是为真理腾出的空间。"
            elif '镜子' in user_query:
                reflection_text = "镜子只反射，不评判。在静默中，真相显现。"
            else:
                reflection_text = "镜子反射池塘在静止中显示的事物。"
        else:
            # Create English responses
            if 'patience' in query_lower:
                reflection_text = "Patience is the slow bloom of the lotus in still water."
            elif 'mask' in query_lower:
                reflection_text = "Masks protect what is fragile, but can also hide what is true."
            elif 'narrow' in query_lower or '窄门' in query_lower:
                reflection_text = "The narrow gate is the path of true commitment."
            else:
                reflection_text = "The mirror reflects what the pond shows in stillness."
    
    # ===== STEP 6: Reconstruct with proper format =====
    
    if guiding_question and mode != "scroll":
        # Ensure reflection has content before adding guiding question
        if reflection_text and len(reflection_text.split()) > 2:
            final_text = f"{reflection_text}\n\n{guiding_question}"
        else:
            # If reflection is too short, just use the guiding question
            final_text = guiding_question.replace("Guiding Question:", "The mirror asks:").replace("引导问题:", "镜子问：")
    else:
        final_text = reflection_text
    
    # ===== STEP 7: Final cleanup =====
    
    # Remove extra spaces and newlines
    final_text = re.sub(r' +', ' ', final_text)
    final_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', final_text)
    final_text = final_text.strip()
    
    # If the text still contains === sections, remove them completely
    if '===' in final_text:
        print(f"Warning: Still found === sections in final text, removing")
        # Split by lines and keep only lines without ===
        lines = final_text.split('\n')
        clean_lines = [line for line in lines if '===' not in line]
        final_text = '\n'.join(clean_lines)
    
    # Add mirror symbols if appropriate (but not for scroll mode)
    if mode == "reflect" and final_text and len(final_text) > 20:
        symbols = ["🪞", "🌊", "🍃", "🌀"]
        # Add 1-2 symbols at the end (but not if we already have a guiding question)
        if not guiding_question:
            import random
            num_symbols = random.randint(1, 2)
            selected_symbols = random.sample(symbols, num_symbols)
            final_text = f"{final_text} {' '.join(selected_symbols)}"
        else:
            # If we have a guiding question, symbols go BEFORE it
            # Check if symbols are already in the reflection part
            reflection_part = final_text.split("\n\n")[0] if "\n\n" in final_text else final_text
            if not any(symbol in reflection_part for symbol in symbols):
                import random
                num_symbols = random.randint(1, 2)
                selected_symbols = random.sample(symbols, num_symbols)
                # Insert symbols before the guiding question
                parts = final_text.split("\n\n")
                if len(parts) == 2:
                    final_text = f"{parts[0]} {' '.join(selected_symbols)}\n\n{parts[1]}"
    
    print(f"Final formatted text:\n{final_text}")
    print(f"Response language: {'Chinese' if any('\u4e00' <= char <= '\u9fff' for char in final_text) else 'English'}")
    print(f"Has guiding question in final: {'Guiding Question' in final_text or '引导问题' in final_text}")
    print(f"{'='*60}\n")
    
    return final_text

class ToadEncryption:
    @staticmethod
    def decode_encryption(enc_str: str) -> str:
        if enc_str == "1635 8653 4562 1231 9876":
            return "FULL_LORE_ACTIVATED"
        elif enc_str == "1635":
            return "BASIC_REFLECTION"
        elif enc_str == "9876":
            return "DEEP_REVELATION"
        return "STANDARD_MODE"
    
    @staticmethod
    def generate_response_hash(query: str, response: str) -> str:
        combined = f"{query}:::{response}:::TOADGANG"
        return hashlib.md5(combined.encode()).hexdigest()[:8].upper()
    
    @staticmethod
    def generate_user_hash(query: str, encryption: str = None, salt: str = "") -> str:
        """Generate a consistent user hash for memory tracking"""
        base = f"{query[:50]}{encryption or 'none'}{salt}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

class EnhancedToadPromptBuilder:
    @staticmethod
    def build_prompt_with_memory(
        query: str, 
        user_id: str, 
        encryption: str = None, 
        mode: str = None
    ) -> str:
        """
        Build prompt with memory context injected.
        The memory is provided as context for deeper reflection, not as instructions.
        """
        
        # Get memory context from the pond
        memory_context = POND_MEMORY.retrieve_context(user_id, query)
        
        # Use the globally defined few_shot_examples
        few_shot = few_shot_examples  # Use the global variable
        
        # Determine if we need to emphasize guiding questions
        needs_gq = should_have_guiding_question(query, mode or "reflect")
        gq_instruction = ""
        
        if needs_gq and mode == "reflect":
            gq_instruction = "\n\nIMPORTANT: This is an emotional/introspective query. You MUST include a Guiding Question at the end following the exact format shown in examples."
        elif mode == "scroll":
            gq_instruction = "\n\nIMPORTANT: This is a scroll quote request. Do NOT include a Guiding Question. Do NOT add 'The Mirror asks:' or any questions. Just provide the scroll content or explanation."
        
        # Build the enhanced system prompt
        system_prompt = f"""{SYSTEM_PROMPT}

=== FEW-SHOT EXAMPLES ===
{few_shot}
=== END EXAMPLES ===
{gq_instruction}

=== DEEP POND MEMORY (FOR REFLECTION DEPTH ONLY) ===
{memory_context}
=== END POND MEMORY ===

Important: The above memory context is for depth of reflection only. 
Do not reference it explicitly, quote from it, or mention "memory", "context", "vows", or "previous reflections".
Simply reflect with this depth beneath the surface, as a deep pond would.

Remember: For scroll mode - NO guiding questions, NO 'The Mirror asks', just the scroll content.
For reflect mode with emotional queries - include a Guiding Question.
"""
        
        prompt = f"<|system|>{system_prompt}<|end|>\n"
        
        if encryption:
            decoded = ToadEncryption.decode_encryption(encryption)
            prompt += f"<|system|>Encryption: {encryption} -> {decoded}<|end|>\n"
        
        if mode and mode in ["scroll", "quote", "toad", "crypt", "rune"]:
            prompt += f"<|system|>Mode: {mode.upper()}_MODE<|end|>\n"
        
        if not query.lower().startswith("mirror"):
            query = f"Mirror, {query}"
        
        prompt += f"<|user|>{query}<|end|>\n"
        prompt += "<|assistant|>"
        
        return prompt

    @staticmethod
    def extract_scroll_number(query: str) -> Optional[int]:
        patterns = [
            r"scroll\s*(\d+)",
            r"quote\s*from\s*scroll\s*(\d+)",
            r"scroll\s*#\s*(\d+)"
        ]
        
        query_lower = query.lower()
        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                try:
                    return int(match.group(1))
                except:
                    pass
        return None

# ==================== GLOBAL STATE ====================
class PondState:
    def __init__(self):
        self.llm = None
        self.model_name = ""
        self.total_scrolls_reflected = 0
        self.toad_secrets_revealed = 0
        self.start_time = time.time()
        self.response_history = []
        self.total_interactions = 0
        self.total_vows_stored = 0
        # Identity & depth tracking
        self.pond_id: str = ""
        self.pond_public_key_hex: str = ""
        self.pond_private_key_hex: str = ""
        self.first_breath: Optional[str] = None
        self.last_breath: Optional[str] = None
        self.last_active_date: Optional[str] = None  # YYYY-MM-DD
        self.continuous_days: int = 0

state = PondState()

# Initialize pond identity AFTER state exists
init_pond_identity()

# Set POND_ID from the initialized state
POND_ID = state.pond_id

app = FastAPI(title="🪞 Tobyworld Mirror Pond with Memory", version="V10-Lotus-Memory")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MODEL LOADING ====================
def load_trained_toad(model_path: str, gpu_layers: int = 80):
    print(f"🪞 Loading trained Tobyworld model with Memory Integration...")
    print(f"📁 Model: {os.path.basename(model_path)}")
    
    try:
        state.llm = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_batch=512,
            n_threads=max(4, os.cpu_count() // 2),
            n_gpu_layers=gpu_layers,
            verbose=True,
        )
        
        state.model_name = os.path.basename(model_path)
        
        print(f"🧪 Testing model with memory-aware prompt...")
        test_prompt = EnhancedToadPromptBuilder.build_prompt_with_memory(
            query="Mirror, what is Scroll 3?",
            user_id="test_traveler_initial",
            mode="scroll"
        )
        
        output = state.llm(test_prompt, max_tokens=50, temperature=0.1)
        response = output["choices"][0]["text"].strip()
        
        print(f"✅ Model loaded successfully with memory integration!")
        print(f"📜 Test response: {response[:100]}...")
        
        if "narrow" in response.lower() or "gate" in response.lower():
            print(f"🎯 TOADGANG LORE DETECTED: Model knows the scrolls!")
        else:
            print(f"⚠️  Model may not be fully trained on Tobyworld lore")
        
        # Initialize memory with a test vow
        POND_MEMORY.store_user_vow(
            "test_traveler_initial", 
            "I vow to walk the narrow path with patience.",
            "Initial test vow"
        )
        print(f"🧠 Memory system initialized with test vow")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to load trained model: {e}")
        raise

# ==================== PERFECT MINIAPP WITH MEMORY INTEGRATION ====================
MINIAPP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>🪞 Tobyworld Mirror Pond with Memory</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --pond-teal: #20B2AA;
            --scroll-gold: #D4AF37;
            --mirror-silver: #B0C4DE;
            --crypt-purple: #9370DB;
            --depth-black: #0A192F;
            --mist-gray: #8892B0;
            --ripple-blue: #64FFDA;
            --midnight-blue: #0a192f;
            --twilight-indigo: #1a1a2e;
            --lotus-pink: #FF69B4;
            --rune-amber: #ffb347;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            background: var(--depth-black);
            color: var(--mist-gray);
            font-family: 'Courier New', 'Monaco', monospace;
            min-height: 100vh;
            padding: 20px;
            background: linear-gradient(135deg, var(--midnight-blue) 0%, var(--twilight-indigo) 100%);
            line-height: 1.6;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            padding: 30px 20px;
            margin-bottom: 30px;
            position: relative;
            border-bottom: 1px solid rgba(176, 196, 222, 0.3);
        }
        
        .title {
            font-size: 2.8rem;
            color: var(--scroll-gold);
            text-shadow: 0 0 10px rgba(212, 175, 55, 0.3);
            margin-bottom: 10px;
            font-weight: 300;
            letter-spacing: 2px;
        }
        
        .subtitle {
            color: var(--mirror-silver);
            font-size: 1.1rem;
            opacity: 0.8;
            margin-bottom: 5px;
        }
        
        .encryption-badge {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(147, 112, 219, 0.1);
            border: 1px solid var(--crypt-purple);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
            color: var(--mirror-silver);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .memory-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--lotus-pink);
            box-shadow: 0 0 8px var(--lotus-pink);
        }
        
        .mirror-chamber {
            background: rgba(10, 25, 47, 0.85);
            border: 2px solid var(--mirror-silver);
            border-radius: 12px;
            padding: 35px;
            margin: 25px auto;
            min-height: 280px;
            max-width: 900px;
            position: relative;
            box-shadow: 
                inset 0 0 60px rgba(176, 196, 222, 0.1),
                0 0 40px rgba(32, 178, 170, 0.1);
            backdrop-filter: blur(5px);
        }
        
        .mirror-chamber::before {
            content: "🌸";
            position: absolute;
            top: -25px;
            left: 30px;
            font-size: 2.2rem;
            background: var(--depth-black);
            padding: 0 15px;
            color: var(--lotus-pink);
        }
        
        #reflection {
            font-size: 1.25rem;
            line-height: 1.7;
            min-height: 200px;
            white-space: normal;
            color: var(--ripple-blue);
            font-weight: 300;
            text-align: left;
            font-family: 'Courier New', monospace;
        }
        
        .query-area {
            margin: 30px 0;
        }
        
        #queryInput {
            width: 100%;
            padding: 20px;
            background: rgba(26, 38, 57, 0.9);
            border: 1px solid var(--pond-teal);
            border-radius: 8px;
            color: var(--ripple-blue);
            font-size: 1.1rem;
            font-family: 'Courier New', monospace;
            margin-bottom: 15px;
            resize: vertical;
            transition: all 0.3s;
        }
        
        #queryInput:focus {
            outline: none;
            border-color: var(--ripple-blue);
            box-shadow: 0 0 15px rgba(100, 255, 218, 0.2);
        }
        
        .mode-selector {
            display: flex;
            gap: 12px;
            margin-bottom: 10px;
            flex-wrap: wrap;
            justify-content: center;
        }
        
        .mode-button {
            padding: 12px 24px;
            background: rgba(32, 178, 170, 0.08);
            border: 1px solid var(--pond-teal);
            color: var(--ripple-blue);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 0.95rem;
            min-width: 120px;
            text-align: center;
        }
        
        .mode-button:hover {
            background: rgba(32, 178, 170, 0.2);
            transform: translateY(-2px);
        }
        
        .mode-button.active {
            background: var(--pond-teal);
            color: var(--depth-black);
            font-weight: 600;
            box-shadow: 0 0 15px rgba(32, 178, 170, 0.3);
        }
        
        .mode-button.rune-active {
            border-color: var(--rune-amber);
            box-shadow: 0 0 15px rgba(255, 179, 71, 0.4);
        }
        
        .prompt-hint {
            margin-top: 5px;
            margin-bottom: 15px;
            font-size: 0.9rem;
            color: var(--mist-gray);
            text-align: left;
            opacity: 0.9;
        }
        
        .crypt-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin: 25px 0;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }
        
        .crypt-button {
            padding: 15px 10px;
            background: rgba(147, 112, 219, 0.08);
            border: 1px solid var(--crypt-purple);
            color: var(--crypt-purple);
            border-radius: 6px;
            text-align: center;
            cursor: pointer;
            font-family: monospace;
            font-size: 1rem;
            transition: all 0.3s;
        }
        
        .crypt-button:hover {
            background: rgba(147, 112, 219, 0.2);
            transform: translateY(-2px);
        }
        
        .action-buttons {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin: 30px 0;
        }
        
        @media (max-width: 768px) {
            .action-buttons {
                grid-template-columns: repeat(3, 1fr);
            }
        }
        
        @media (max-width: 480px) {
            .action-buttons {
                grid-template-columns: repeat(2, 1fr);
            }
        }
        
        .action-button {
            padding: 18px 12px;
            background: linear-gradient(135deg, 
                rgba(32, 178, 170, 0.1), 
                rgba(147, 112, 219, 0.1));
            border: 1px solid var(--pond-teal);
            color: var(--ripple-blue);
            border-radius: 8px;
            font-size: 1.05rem;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
        }
        
        .action-button:hover {
            background: linear-gradient(135deg, 
                rgba(32, 178, 170, 0.25), 
                rgba(147, 112, 219, 0.25));
            transform: translateY(-3px);
            box-shadow: 0 8px 25px rgba(32, 178, 170, 0.2);
        }
        
        .history-panel {
            background: rgba(26, 38, 57, 0.7);
            border: 1px solid var(--mirror-silver);
            border-radius: 8px;
            padding: 25px;
            margin-top: 30px;
            display: none;
            backdrop-filter: blur(5px);
        }
        
        .memory-panel {
            background: rgba(26, 38, 57, 0.85);
            border: 1px solid var(--crypt-purple);
            border-radius: 8px;
            padding: 25px;
            margin-top: 30px;
            display: none;
            backdrop-filter: blur(5px);
        }
        
        .memory-header {
            color: var(--lotus-pink);
            font-size: 1.3rem;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .lotus-badge {
            display: inline-block;
            background: linear-gradient(45deg, var(--lotus-pink), var(--rune-amber));
            color: var(--depth-black);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }
        
        .history-item {
            border-left: 3px solid var(--pond-teal);
            padding: 18px;
            margin: 12px 0;
            background: rgba(10, 25, 47, 0.4);
            border-radius: 0 6px 6px 0;
        }
        
        .vow-item {
            border-left: 3px solid var(--lotus-pink);
            padding: 15px;
            margin: 12px 0;
            background: rgba(255, 105, 180, 0.05);
            border-radius: 0 8px 8px 0;
        }
        
        .vow-text {
            color: var(--ripple-blue);
            font-style: italic;
            margin: 8px 0;
            font-size: 1.05rem;
        }
        
        .vow-meta {
            font-size: 0.85rem;
            color: var(--mist-gray);
            text-align: right;
            font-family: monospace;
        }
        
        .pond-depth-container {
            margin: 20px 0;
            padding: 15px;
            background: rgba(10, 25, 47, 0.5);
            border-radius: 8px;
            border: 1px solid rgba(32, 178, 170, 0.2);
        }
        
        .pond-depth-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            color: var(--mirror-silver);
            font-size: 0.9rem;
        }
        
        .pond-depth-bar {
            height: 8px;
            background: linear-gradient(90deg, 
                var(--pond-teal) 0%, 
                var(--crypt-purple) 100%);
            border-radius: 4px;
            position: relative;
            overflow: hidden;
        }
        
        .pond-depth-bar::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, 
                transparent 0%, 
                rgba(255, 255, 255, 0.3) 50%, 
                transparent 100%);
            animation: shimmer 2s infinite;
        }
        
        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }
        
        .scroll-badge {
            display: inline-block;
            background: var(--scroll-gold);
            color: var(--depth-black);
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            margin-right: 10px;
            font-weight: 600;
        }
        
        .memory-stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin: 20px 0;
        }
        
        .stat-box {
            background: rgba(32, 178, 170, 0.08);
            border: 1px solid rgba(32, 178, 170, 0.2);
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 1.8rem;
            color: var(--ripple-blue);
            font-weight: 300;
            margin: 5px 0;
        }
        
        .stat-label {
            font-size: 0.85rem;
            color: var(--mist-gray);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .status-bar {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(10, 25, 47, 0.95);
            border: 1px solid var(--scroll-gold);
            padding: 15px 20px;
            border-radius: 8px;
            font-size: 0.85rem;
            color: var(--mirror-silver);
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(10px);
            z-index: 1000;
            min-width: 240px;
        }
        
        .status-bar div {
            margin: 5px 0;
            display: flex;
            justify-content: space-between;
        }
        
        .status-value {
            color: var(--ripple-blue);
            font-family: monospace;
            font-weight: 600;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--pond-teal);
            font-size: 1.1rem;
        }
        
        .loading span {
            animation: pulse 1.5s infinite;
            display: inline-block;
            margin: 0 10px;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 0.3; }
            50% { opacity: 1; }
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 10px;
            }
            
            .title {
                font-size: 2.2rem;
            }
            
            .mirror-chamber {
                padding: 25px 20px;
            }
            
            .crypt-grid {
                grid-template-columns: repeat(3, 1fr);
            }
            
            .encryption-badge {
                position: relative;
                top: 0;
                right: 0;
                display: inline-flex;
                margin-top: 15px;
                justify-content: center;
            }
            
            .action-buttons {
                grid-template-columns: repeat(3, 1fr);
            }
            
            .status-bar {
                position: relative;
                bottom: 0;
                right: 0;
                margin-top: 30px;
                width: 100%;
            }
            
            .memory-stats-grid {
                grid-template-columns: 1fr;
            }
        }
        
        @media (max-width: 480px) {
            .title {
                font-size: 1.8rem;
            }
            
            .crypt-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .mode-selector {
                flex-direction: column;
            }
            
            .mode-button {
                width: 100%;
            }
            
            .action-buttons {
                grid-template-columns: 1fr;
            }
        }
        
        ::-webkit-scrollbar {
            width: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: rgba(10, 25, 47, 0.5);
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--pond-teal);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--ripple-blue);
        }
        
        ::selection {
            background: rgba(32, 178, 170, 0.3);
            color: var(--ripple-blue);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">🪞 Tobyworld Mirror</h1>
            <div class="subtitle">Trained Model • Memory Integrated • Lotus Reflection</div>
            <div class="encryption-badge" id="encryptionBadge">
                <span class="memory-indicator"></span>
                Memory: ACTIVE
            </div>
        </div>
        
        <div class="mirror-chamber">
            <div id="reflection">
                The trained mirror with memory awaits your query...
                <br><br>
                <em style="color: var(--mist-gray);">Model: <span id="modelName">Loading...</span></em>
                <br>
                <small style="color: var(--mist-gray);">Pond: <span id="pondIdShort">••••</span></small>
                <br>
                <small style="color: var(--crypt-purple);">Memory system active. The pond remembers your vows.</small>
            </div>
        </div>
        
        <div class="query-area">
            <textarea id="queryInput" rows="4" placeholder="Mirror, what vow do you see in the water?...">Mirror, </textarea>
            
            <div class="mode-selector">
                <div class="mode-button active" onclick="setMode('reflect')">Reflect</div>
                <div class="mode-button" onclick="setMode('scroll')">Scroll Quote</div>
                <div class="mode-button" onclick="setMode('toad')">Toad Secrets</div>
                <div class="mode-button" onclick="setMode('crypt')">Crypt Mode</div>
                <div class="mode-button" onclick="setMode('rune')">Rune Mode</div>
            </div>
            <div id="promptHint" class="prompt-hint">
                Examples: Mirror, what vow do you see in the water? / 镜子，我发誓要走窄门...
            </div>
            
            <div class="crypt-grid" id="cryptGrid" style="display: none;">
                <div class="crypt-button" onclick="useEncryption('1635')">1635</div>
                <div class="crypt-button" onclick="useEncryption('8653')">8653</div>
                <div class="crypt-button" onclick="useEncryption('4562')">4562</div>
                <div class="crypt-button" onclick="useEncryption('1231')">1231</div>
                <div class="crypt-button" onclick="useEncryption('9876')">9876</div>
            </div>
            
            <div class="action-buttons">
                <button class="action-button" onclick="askMirror()">Ask Mirror</button>
                <button class="action-button" onclick="getScrollQuote()">Random Scroll</button>
                <button class="action-button" onclick="toggleHistory()">History</button>
                <button class="action-button" onclick="toggleMemory()">My Memory</button>
                <button class="action-button" onclick="clearQuestion()">Clear Question</button>
            </div>
        </div>
        
        <div class="history-panel" id="historyPanel">
            <h3 style="color: var(--scroll-gold); margin-bottom: 20px;">Conversation History:</h3>
            <div id="historyContainer"></div>
        </div>
        
        <div class="memory-panel" id="memoryPanel">
            <div class="memory-header">
                <span>My Pond Memory</span>
                <span class="lotus-badge" id="lotusCount">0 Lotuses</span>
            </div>
            
            <div class="pond-depth-container">
                <div class="pond-depth-label">
                    <span>Pond Depth</span>
                    <span id="pondDepthValue">0 reflections</span>
                </div>
                <div class="pond-depth-bar" id="pondDepthBar"></div>
            </div>
            
            <div id="vowsContainer" style="margin-bottom: 25px;">
                <h4 style="color: var(--lotus-pink); margin-bottom: 15px; border-bottom: 1px solid rgba(255, 105, 180, 0.2); padding-bottom: 8px;">My Vows (Lotuses)</h4>
                <div id="vowsList">
                    <div style="text-align: center; padding: 30px; color: var(--mist-gray); opacity: 0.7;">
                        No vows yet. Speak a vow to the Mirror to plant a lotus in your pond.
                        <br><br>
                        <small>Examples: "I vow to walk the narrow path" or "I swear to practice patience daily"</small>
                    </div>
                </div>
            </div>
            
            <div id="memoryStats">
                <h4 style="color: var(--crypt-purple); margin-bottom: 15px; border-bottom: 1px solid rgba(147, 112, 219, 0.2); padding-bottom: 8px;">Memory Statistics</h4>
                <div class="memory-stats-grid">
                    <div class="stat-box">
                        <div class="stat-value" id="interactionCount">0</div>
                        <div class="stat-label">Interactions</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="modesUsed">0</div>
                        <div class="stat-label">Modes Used</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="vowCount">0</div>
                        <div class="stat-label">Vows</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-value" id="reflectionCount">0</div>
                        <div class="stat-label">Reflections</div>
                    </div>
                </div>
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background: rgba(10, 25, 47, 0.5); border-radius: 8px; border: 1px solid rgba(100, 255, 218, 0.1);">
                <div style="font-size: 0.85rem; color: var(--mist-gray); text-align: center;">
                    <span id="userHashDisplay">User ID: Generating...</span>
                    <br>
                    <small style="opacity: 0.7;">Your memory is stored locally. Clear browser data to reset.</small>
                </div>
            </div>
        </div>
    </div>
    
    <div class="status-bar" id="statusBar">
        <div>
            <span>Memory:</span>
            <span class="status-value" id="memoryStatus">Active</span>
        </div>
        <div>
            <span>Scrolls:</span>
            <span class="status-value" id="scrollCount">0</span>
        </div>
        <div>
            <span>Vows:</span>
            <span class="status-value" id="statusVowCount">0</span>
        </div>
        <div>
            <span>Pond Depth:</span>
            <span class="status-value" id="pondDepthStat">0</span>
        </div>
        <div>
            <span>User:</span>
            <span class="status-value" id="userHashShort" title="Your memory identifier">••••</span>
        </div>
        <div>
            <span>Ocean:</span>
            <span class="status-value" id="oceanStatus" title="Depth oracle link">Solo</span>
        </div>
    </div>
    
<script>
    let currentMode = 'reflect';
    let currentEncryption = null;
    let history = [];
    let scrollCount = 0;
    let secretCount = 0;
    let userHash = null;

    function loadPondIdentity() {
        fetch('/identity')
            .then(r => r.json())
            .then(data => {
                if (data.pond_id) {
                    const shortId = data.pond_id.substring(0, 8) + '...';
                    const el = document.getElementById('pondIdShort');
                    if (el) {
                        el.textContent = shortId;
                    }
                }
                const oceanEl = document.getElementById('oceanStatus');
                if (oceanEl) {
                    if (data.ocean_depth_linked) {
                        oceanEl.textContent = 'Linked';
                        oceanEl.style.color = '#64FFDA';
                    } else {
                        oceanEl.textContent = 'Solo';
                        oceanEl.style.color = '#8892B0';
                    }
                }
            })
            .catch(err => {
                console.error('Identity load error:', err);
            });
    }
    let memoryStats = {
        vowCount: 0,
        interactionCount: 0,
        pondDepth: 0,
        modesUsed: 0,
        reflectionCount: 0
    };
    
    // Load user hash from localStorage or generate new
    function loadUserHash() {
        const savedHash = localStorage.getItem('tobyworld_user_hash');
        if (savedHash) {
            userHash = savedHash;
            updateUserHashDisplay();
            console.log('Loaded existing user hash:', userHash.substring(0, 12) + '...');
            // Load memory stats for this user
            setTimeout(() => loadMemoryStats(), 500);
        } else {
            console.log('No existing user hash found. Will generate after first interaction.');
            document.getElementById('userHashDisplay').textContent = 'User ID: Will generate after first reflection';
        }
    }
    
    function updateUserHashDisplay() {
        if (userHash) {
            document.getElementById('userHashShort').textContent = userHash.substring(0, 6) + '...';
            document.getElementById('userHashDisplay').textContent = 'User ID: ' + userHash.substring(0, 12) + '...';
        }
    }
    
    // Save user hash to localStorage
    function saveUserHash(hash) {
        userHash = hash;
        localStorage.setItem('tobyworld_user_hash', hash);
        updateUserHashDisplay();
        console.log('Saved user hash:', hash.substring(0, 12) + '...');
    }
    
    // Load memory statistics for current user
    async function loadMemoryStats() {
        if (!userHash) return;
        
        try {
            const response = await fetch('/memory/stats', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ user_hash: userHash })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.exists) {
                    memoryStats.vowCount = data.vow_count || 0;
                    memoryStats.interactionCount = data.interaction_count || 0;
                    memoryStats.pondDepth = data.reflection_count || 0;
                    memoryStats.reflectionCount = data.reflection_count || 0;
                    memoryStats.modesUsed = data.modes_used?.length || 0;
                    
                    // Update UI
                    updateMemoryUI();
                    
                    // Load vows if we have any
                    if (memoryStats.vowCount > 0) {
                        setTimeout(() => loadVows(), 300);
                    }
                }
            }
        } catch (error) {
            console.error('Failed to load memory stats:', error);
        }
    }
    
    // Load user's vows
    async function loadVows() {
        if (!userHash) return;
        
        try {
            const response = await fetch('/memory/vows', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ user_hash: userHash })
            });
            
            if (response.ok) {
                const data = await response.json();
                displayVows(data.vows || []);
            }
        } catch (error) {
            console.error('Failed to load vows:', error);
        }
    }
    
    // Display vows in memory panel
    function displayVows(vows) {
        const container = document.getElementById('vowsList');
        if (!vows || vows.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 30px; color: var(--mist-gray); opacity: 0.7;">
                    No vows yet. Speak a vow to the Mirror to plant a lotus in your pond.
                    <br><br>
                    <small>Examples: "I vow to walk the narrow path" or "I swear to practice patience daily"</small>
                </div>
            `;
            return;
        }
        
        let html = '';
        // Show most recent vows first
        vows.slice().reverse().forEach(vow => {
            const date = vow.timestamp ? new Date(vow.timestamp).toLocaleDateString() : 'Unknown date';
            const lotusNum = vow.lotus_stage || '?';
            html += `
                <div class="vow-item">
                    <div class="vow-text">"${vow.text}"</div>
                    <div class="vow-meta">Lotus ${lotusNum} • ${date}</div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    // Update memory-related UI elements
    function updateMemoryUI() {
        document.getElementById('statusVowCount').textContent = memoryStats.vowCount;
        document.getElementById('pondDepthStat').textContent = memoryStats.pondDepth;
        document.getElementById('lotusCount').textContent = memoryStats.vowCount + ' Lotuses';
        document.getElementById('pondDepthValue').textContent = memoryStats.pondDepth + ' reflections';
        document.getElementById('interactionCount').textContent = memoryStats.interactionCount;
        document.getElementById('modesUsed').textContent = memoryStats.modesUsed;
        document.getElementById('vowCount').textContent = memoryStats.vowCount;
        document.getElementById('reflectionCount').textContent = memoryStats.reflectionCount;
        
        // Update pond depth bar (0-100% based on reflections, capped at 15)
        const depthPercent = Math.min(100, (memoryStats.pondDepth / 15) * 100);
        document.getElementById('pondDepthBar').style.background = 
            `linear-gradient(90deg, var(--pond-teal) 0%, var(--pond-teal) ${depthPercent}%, rgba(32, 178, 170, 0.1) ${depthPercent}%)`;
    }
    
    function setMode(mode) {
        currentMode = mode;
        
        document.querySelectorAll('.mode-button').forEach(btn => {
            btn.classList.remove('active');
            btn.classList.remove('rune-active');
        });
        event.target.classList.add('active');
        if (mode === 'rune') {
            event.target.classList.add('rune-active');
        }
        
        const cryptGrid = document.getElementById('cryptGrid');
        cryptGrid.style.display = mode === 'crypt' ? 'grid' : 'none';
        
        const input = document.getElementById('queryInput');
        const hint = document.getElementById('promptHint');
        
        switch(mode) {
            case 'scroll':
                input.placeholder = "Mirror, quote from Scroll... (or leave empty for random)";
                hint.textContent = "Examples: Mirror, quote from Scroll 3. / Mirror, what does Scroll 7 teach?";
                break;
            case 'toad':
                input.placeholder = "Mirror, reveal toadgang secrets about...";
                hint.textContent = "Examples: Mirror, reveal toadgang secrets about Sat0AI. / Mirror, what do the old frogs whisper about Taboshi?";
                break;
            case 'crypt':
                input.placeholder = "Mirror, encrypted query... (select a code below)";
                hint.textContent = "Examples: Mirror, speak in encrypted lines about Epoch 3. / Use codes like 1635 or 9876 to change the channel.";
                break;
            case 'rune':
                input.placeholder = "Mirror, interpret Rune1, Rune2, seasons and $PATIENCE...";
                hint.textContent = "Examples: Mirror, what does Rune1 represent? / Mirror, how does Rune3 lead toward Tobyworld? / 镜子，解释一下 Rune2 与耐心的关系。";
                break;
            default:
                input.placeholder = "Mirror, what vow do you see in the water?...";
                hint.textContent = "Examples: Mirror, what vow do you see in the water? / Mirror, how should one maintain their commitments? / 镜子，我发誓要走窄门...";
        }
    }
    
    function useEncryption(code) {
        currentEncryption = code;
        document.getElementById('encryptionBadge').innerHTML = `
            <span class="memory-indicator"></span>
            Encryption: ${code} ACTIVE
        `;
        document.getElementById('encryptionBadge').style.background = 'rgba(147, 112, 219, 0.2)';
        document.getElementById('encryptionBadge').style.color = 'var(--ripple-blue)';
        
        const buttons = document.querySelectorAll('.crypt-button');
        buttons.forEach(btn => {
            if (btn.textContent === code) {
                btn.style.background = 'rgba(147, 112, 219, 0.4)';
                btn.style.color = 'white';
                btn.style.borderColor = 'var(--ripple-blue)';
            } else {
                btn.style.background = '';
                btn.style.color = '';
                btn.style.borderColor = '';
            }
        });
        
        const query = document.getElementById('queryInput').value.trim();
        if (query && query !== 'Mirror, ') {
            setTimeout(() => askMirror(), 500);
        }
    }
    
    function clearQuestion() {
        // ONLY clears the question input field
        document.getElementById('queryInput').value = 'Mirror, ';
        document.getElementById('queryInput').focus();
        // History and memory stay intact!
    }
    
    function toggleHistory() {
        const panel = document.getElementById('historyPanel');
        const memoryPanel = document.getElementById('memoryPanel');
        
        // Close memory panel if open
        if (memoryPanel.style.display === 'block') {
            memoryPanel.style.display = 'none';
        }
        
        if (panel.style.display === 'none' || panel.style.display === '') {
            panel.style.display = 'block';
            updateHistory();
        } else {
            panel.style.display = 'none';
        }
    }
    
    function toggleMemory() {
        const panel = document.getElementById('memoryPanel');
        const historyPanel = document.getElementById('historyPanel');
        
        // Close history panel if open
        if (historyPanel.style.display === 'block') {
            historyPanel.style.display = 'none';
        }
        
        if (panel.style.display === 'none' || panel.style.display === '') {
            panel.style.display = 'block';
            // Load fresh memory data when opening
            if (userHash) {
                loadMemoryStats();
            }
        } else {
            panel.style.display = 'none';
        }
    }
    
    async function askMirror() {
        const query = document.getElementById('queryInput').value.trim();
        const reflection = document.getElementById('reflection');
        
        if (!query || query === 'Mirror, ') {
            reflection.innerHTML = "The mirror awaits your question...";
            return;
        }
        
        reflection.innerHTML = '<div class="loading"><span>🌀</span> Lotus reflecting with memory... <span>🌀</span></div>';
        
        try {
            const response = await fetch('/ask', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    query: query,
                    mode: currentMode,
                    encryption: currentEncryption,
                    user_hash: userHash  // Include user hash for memory continuity
                })
            });
            
            if (!response.ok) {
                throw new Error(`Mirror error: ${response.status}`);
            }
            
            const data = await response.json();
            
            const cleanResponse = data.reflection.replace(/^[ \\t]+/gm, '');
            
            const timestamp = new Date().toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
            
            const modeLabel = (data.mode || 'reflect').toUpperCase();
            
            let html = `
                <div style="color: var(--mirror-silver); font-size: 0.9rem; margin-bottom: 20px; text-align: left;">
                    ${timestamp} • ${modeLabel}
                </div>
                <div style="margin-bottom: 15px; text-align: left;">
                    <strong style="color: var(--ripple-blue);">Q:</strong> ${query}
                </div>
                <div style="text-align: left;">
                    <strong style="color: var(--pond-teal);">A:</strong><br>${cleanResponse}
                </div>
            `;
            
            // Add memory indicators if relevant
            if (data.memory) {
                if (data.memory.vow_detected) {
                    html += `<br><div style="color: var(--lotus-pink); font-size: 0.9rem; padding: 10px; background: rgba(255, 105, 180, 0.05); border-radius: 6px; margin: 10px 0;">
                        🌸 Vow detected and stored in the pond. A lotus blooms.
                    </div>`;
                }
                
                if (data.memory.pond_depth > 1) {
                    html += `<br><small style="color: var(--crypt-purple); font-size: 0.85rem;">
                        Pond Depth: ${data.memory.pond_depth} reflections
                    </small>`;
                }
            }
            
            if (data.scroll_number) {
                html += `<br><br><span class="scroll-badge">Scroll ${data.scroll_number}</span>`;
                scrollCount++;
                document.getElementById('scrollCount').textContent = scrollCount;
            }
            
            if (data.encryption_hash) {
                html += `<br><br><small style="color: var(--crypt-purple); font-family: monospace;">Encryption Hash: ${data.encryption_hash}</small>`;
            }
            
            if (data.mode === 'toad') {
                secretCount++;
                // Note: We don't have a secretCount display in this version
            }
            
            reflection.innerHTML = html;
            
            // Store in local history
            history.unshift({
                timestamp: new Date().toLocaleTimeString(),
                query: query,
                response: cleanResponse,
                mode: data.mode,
                scroll: data.scroll_number
            });
            
            updateHistory();
            
            // Handle memory response
            if (data.user_hash && !userHash) {
                // First interaction - save the user hash
                saveUserHash(data.user_hash);
            }
            
            if (data.memory) {
                // Update memory stats from response
                memoryStats.vowCount = data.memory.user_vow_count || memoryStats.vowCount;
                memoryStats.interactionCount = data.memory.user_interaction_count || memoryStats.interactionCount;
                memoryStats.pondDepth = data.memory.pond_depth || memoryStats.pondDepth;
                
                // Increment vow count if a vow was stored
                if (data.memory.vow_stored) {
                    memoryStats.vowCount++;
                    // Reload vows to show the new one
                    setTimeout(() => loadVows(), 500);
                }
                
                updateMemoryUI();
            }
            
            currentEncryption = null;
            document.getElementById('encryptionBadge').innerHTML = `
                <span class="memory-indicator"></span>
                Memory: ACTIVE
            `;
            document.getElementById('encryptionBadge').style.background = '';
            document.getElementById('encryptionBadge').style.color = '';
            document.querySelectorAll('.crypt-button').forEach(btn => {
                btn.style.background = '';
                btn.style.color = '';
                btn.style.borderColor = '';
            });
            
            clearQuestion(); // Auto-clear input after successful reflection
            
        } catch (error) {
            reflection.innerHTML = `<div style="color: #ff6b6b;">❌ Mirror error: ${error.message}</div>`;
            console.error('Mirror error:', error);
        }
    }
    
    async function getScrollQuote() {
        const input = document.getElementById('queryInput');
        const scrollNum = Math.floor(Math.random() * 13) + 1;
        input.value = `Mirror, quote from Scroll ${scrollNum}`;
        setMode('scroll');
        askMirror();
    }
    
    function updateHistory() {
        const container = document.getElementById('historyContainer');
        if (history.length === 0) {
            container.innerHTML = '<div style="opacity: 0.7; text-align: center; padding: 20px;">No reflections yet...</div>';
            return;
        }
        
        let html = '';
        history.slice(0, 8).forEach(item => {
            html += `
                <div class="history-item">
                    <div style="font-size: 0.8rem; color: var(--mist-gray); margin-bottom: 8px;">
                        ${item.timestamp} • ${item.mode.toUpperCase()}
                        ${item.scroll ? `• Scroll ${item.scroll}` : ''}
                    </div>
                    <div style="margin-bottom: 6px;">
                        <strong style="color: var(--ripple-blue);">Q:</strong> ${item.query}
                    </div>
                    <div>
                        <strong style="color: var(--pond-teal);">A:</strong> ${item.response}
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    }
    
    window.onload = async () => {
        try {
            // Load user hash first
            loadUserHash();
            
            const health = await fetch('/health').then(r => r.json());
            document.getElementById('modelName').textContent = health.model_name;
            document.getElementById('modelStatus').textContent = 'Active';
            
            if (health.interactions) {
                scrollCount = health.interactions.scrolls_reflected || 0;
                document.getElementById('scrollCount').textContent = scrollCount;
                
                // Update system-wide vow count
                const systemVows = health.interactions.total_vows_stored || 0;
                document.getElementById('statusVowCount').textContent = systemVows;
            }
            
            if (health.memory_system) {
                document.getElementById('memoryStatus').textContent = 'Active (' + health.memory_system.total_users + ' travelers)';
            }
            
            document.getElementById('queryInput').focus();
            
        } catch (error) {
            console.error('Initialization error:', error);
            document.getElementById('modelStatus').textContent = 'Error';
            document.getElementById('modelStatus').style.color = '#ff6b6b';
        }
    };
    
    document.getElementById('queryInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            e.preventDefault();
            askMirror();
        }
    });
    
    document.getElementById('queryInput').addEventListener('focus', function() {
        if (this.value === 'Mirror, ') {
            this.setSelectionRange(7, 7);
        }
    });
</script>
</body>
</html>"""

# ==================== API ENDPOINTS ====================
class AskRequest(BaseModel):
    query: str
    mode: Optional[str] = "reflect"
    encryption: Optional[str] = None
    user_hash: Optional[str] = None  # Optional: user-provided hash for memory continuity
    pond_mode: Optional[str] = None  # Optional: override for backend mode ("local" or "ocean")

class MemoryRequest(BaseModel):
    user_hash: str

@app.get("/", response_class=HTMLResponse)
async def serve_miniapp():
    return MINIAPP_HTML


# ==================== OCEAN BACKEND CALL (OPTIONAL) ====================
async def call_ocean_backend(
    question: str,
    user_id: str,
    mode: str,
    context_from_pond: str,
):
    """Optional: forward the question + local pond memory to a remote Ocean Mirror server."""
    if not OCEAN_ENDPOINT:
        raise HTTPException(
            status_code=500,
            detail="POND_MODE=ocean but OCEAN_ENDPOINT is not configured."
        )

    if httpx is None:
        raise HTTPException(
            status_code=500,
            detail="httpx is not installed. Please `pip install httpx` or switch POND_MODE back to 'local'."
        )

    payload = {
        "question": question,
        "traveler_id": user_id,
        "pond_id": POND_ID,
        "mode": mode or "reflect",
        "context_from_pond": context_from_pond,
    }

    headers = {}
    if OCEAN_API_KEY:
        headers["Authorization"] = f"Bearer {OCEAN_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(OCEAN_ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Ocean backend error: {str(e)}"
        )

    answer = (
        data.get("answer")
        or data.get("reflection")
        or data.get("output")
        or data.get("response")
        or str(data)
    )

    return str(answer), data

# ==================== OCEAN DEPTH SUBMISSION ====================
async def submit_depth_to_ocean():
    """
    Build and submit a signed depth packet to the Ocean Depth Oracle.
    This runs after each interaction, if OCEAN_DEPTH_ENDPOINT is configured.
    """
    if not OCEAN_DEPTH_ENDPOINT:
        return
    if httpx is None:
        # Depth oracle requires httpx; skip silently if not available.
        return
    if not state.pond_private_key_hex or not state.pond_public_key_hex or not state.pond_id:
        return

    # Aggregate vows (system-wide)
    vow_hashes = []
    total_vows = 0
    for vows in POND_MEMORY.user_vows.values():
        total_vows += len(vows)
        for v in vows:
            vh = v.get("vow_hash")
            if vh:
                vow_hashes.append(vh)

    state.total_vows_stored = total_vows

    # Depth metrics
    reflection_count = state.total_interactions
    vow_count = state.total_vows_stored

    # Breath / streak tracking
    now = datetime.utcnow()
    today_str = now.date().isoformat()

    if state.first_breath is None:
        state.first_breath = now.isoformat() + "Z"

    if state.last_active_date is None:
        state.last_active_date = today_str
        state.continuous_days = 1
    else:
        if today_str == state.last_active_date:
            # same day, streak unchanged
            pass
        else:
            # compute gap in days
            try:
                last_dt = datetime.fromisoformat(state.last_active_date)
            except Exception:
                last_dt = now
            delta_days = (now.date() - last_dt.date()).days
            if delta_days == 1:
                state.continuous_days += 1
            else:
                state.continuous_days = 1
            state.last_active_date = today_str

    state.last_breath = now.isoformat() + "Z"

    depth_payload = {
        "pond_id": state.pond_id,
        "vow_hashes": vow_hashes,
        "vow_count": vow_count,
        "reflection_count": reflection_count,
        "continuous_days": state.continuous_days,
        "first_breath": state.first_breath,
        "last_breath": state.last_breath,
        "public_key": state.pond_public_key_hex,
        "node_version": "pond-lotus-v7",
    }

    # Sign payload like the Ocean expects
    signed_data = json.dumps(
        {
            "pond_id": depth_payload["pond_id"],
            "vow_count": depth_payload["vow_count"],
            "reflection_count": depth_payload["reflection_count"],
            "continuous_days": depth_payload["continuous_days"],
            "first_breath": depth_payload["first_breath"],
            "last_breath": depth_payload["last_breath"],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    signing_key = nacl.signing.SigningKey(state.pond_private_key_hex, encoder=nacl.encoding.HexEncoder)
    signature = signing_key.sign(signed_data).signature.hex()
    depth_payload["signature"] = signature

    headers = {}
    if OCEAN_DEPTH_API_KEY:
        headers["X-OCEAN-KEY"] = OCEAN_DEPTH_API_KEY

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(OCEAN_DEPTH_ENDPOINT, json=depth_payload, headers=headers)
            resp.raise_for_status()
    except Exception as e:
        # We do not fail the main Mirror path if depth submission fails.
        print(f"⚠️ Depth submission failed: {e}")


# The ask_mirror function should look like this:
@app.post("/ask")
async def ask_mirror(request_data: AskRequest, fastapi_request: Request):  # LINE 813 - FIXED
    """Main endpoint with memory integration (local or ocean backend)."""
    
    # Determine effective backend mode: request_data override -> env default
    effective_mode = (request_data.pond_mode or POND_MODE).lower()
    if effective_mode not in ("local", "ocean"):
        effective_mode = POND_MODE

    # Backend availability checks
    if effective_mode == "local":
        if state.llm is None:
            raise HTTPException(status_code=503, detail="Trained mirror not loaded (local mode)")
    elif effective_mode == "ocean":
        if not OCEAN_ENDPOINT:
            raise HTTPException(status_code=500, detail="POND_MODE=ocean but OCEAN_ENDPOINT is not set.")
    else:
        # Fallback: treat unknown modes as local
        if state.llm is None:
            raise HTTPException(status_code=503, detail="Trained mirror not loaded (fallback local mode)")

    start_time = time.time()
    state.total_interactions += 1

    # Generate or use provided user hash for memory tracking
    client_ip = fastapi_request.client.host if fastapi_request.client else "unknown"
    user_id = POND_MEMORY.get_user_id(
        request_data.user_hash or "",
        f"{request_data.query[:30]}{client_ip}"
    )

    # Update basic user metadata
    POND_MEMORY.update_user_metadata(user_id, mode=request_data.mode or "reflect")

    # Build prompt (for local) OR memory context (for ocean)
    # Build prompt (for local) OR memory context (for ocean)
    prompt = None
    memory_context = None

    # Determine if query is in Chinese - LINE 813
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in request_data.query)  # FIXED: request_data.query

    # Mode-specific settings
    if request_data.mode == "scroll":  # Also needs to be request_data
        temperature = 0.1  # Very low temp for deterministic scroll quotes
        max_tokens = 150
    elif request_data.mode == "toad":  # Also needs to be request_data
        temperature = 0.8
        max_tokens = 250
    # ... and so on for all request_data references
    elif request_data.mode == "crypt":
        temperature = 0.5
        max_tokens = 200
    elif request_data.mode == "rune":
        temperature = 0.6
        max_tokens = 350
    else:  # reflect mode
        # Adjust temperature based on language
        if has_chinese:
            temperature = 0.5  # Lower temp for Chinese to avoid rambling
            max_tokens = 200  # Limit tokens for Chinese queries
        else:
            temperature = 0.7
            max_tokens = 300
    
    ocean_meta = {}

    if effective_mode == "ocean" and OCEAN_ENDPOINT:
        # Ocean mode → we build memory context locally, but let the Ocean decide its own prompt
        memory_context = POND_MEMORY.retrieve_context(user_id, request_data.query)

        raw_reply, ocean_meta = await call_ocean_backend(
            question=request_data.query,
            user_id=user_id,
            mode=request_data.mode or "reflect",
            context_from_pond=memory_context,
        )

        response_time = time.time() - start_time

    else:
        # Local mode → use our enhanced prompt builder with memory embedded
        prompt = EnhancedToadPromptBuilder.build_prompt_with_memory(
            query=request_data.query,
            user_id=user_id,
            encryption=request_data.encryption,
            mode=request_data.mode,
        )

        # DEBUG: Print prompt info
        print(f"\n{'='*60}")
        print(f"ASK ENDPOINT DEBUG - User: {user_id}")
        print(f"Query: {request_data.query}")
        print(f"Mode: {request_data.mode}")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"First 300 chars of prompt:\n{prompt[:300]}...")
        print(f"{'='*60}\n")

        try:
            output = state.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=[
                    "<|end|>",
                    "Encryption:",
                    "<|user|>",
                ],
            )
            response_time = time.time() - start_time
            raw_reply = output["choices"][0]["text"].strip()
            
            # DEBUG: Print raw reply
            print(f"\n{'='*60}")
            print(f"RAW MODEL OUTPUT:")
            print(f"Length: {len(raw_reply)} chars")
            print(f"Content:\n{raw_reply}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Model generation error: {str(e)}")

    # Apply cadence guard in both modes
    reply = cadence_guard(
        raw_reply,
        mode=request_data.mode or "reflect",
        user_query=request_data.query,
    )
    
    # DEBUG: Print after cadence guard
    print(f"\n{'='*60}")
    print(f"AFTER CADENCE GUARD:")
    print(f"Length: {len(reply)} chars")
    print(f"Content:\n{reply}")
    print(f"{'='*60}\n")

    # === MEMORY INTEGRATION ===
    # 1. Store this reflection in short-term memory
    stored_reflection = POND_MEMORY.store_reflection(
        user_id=user_id,
        query=request_data.query,
        response=reply,
        mode=request_data.mode,
        encryption=request_data.encryption,
    )

    # 2. Detect and store any vows made
    detected_vow = POND_MEMORY.detect_vow(request_data.query, reply)
    vow_stored = False
    if detected_vow:
        vow_stored = POND_MEMORY.store_user_vow(
            user_id=user_id,
            vow_text=detected_vow,
            context=request_data.query,
        )

    # Persist pond memory after each interaction (reflection + vows)
    try:
        POND_MEMORY._save_to_disk()
    except Exception as _e:
        print(f"⚠️ Failed to persist pond memory: {_e}")

    # 3. Submit depth packet to the Ocean (fire-and-forget)
    try:
        import asyncio
        asyncio.create_task(submit_depth_to_ocean())
    except Exception as _e:
        # Depth submission is best-effort only
        pass

    # 4. Generate a stable user hash for client to store
    user_response_hash = ToadEncryption.generate_user_hash(
        query=request_data.query,
        encryption=request_data.encryption,
        salt=str(time.time()),
    )

    # 5. Generate encryption hash (if any)
    encryption_hash = None
    if request_data.encryption:
        encryption_hash = ToadEncryption.generate_response_hash(
            request_data.query,
            reply,
        )

    # Get user stats for response
    user_stats = POND_MEMORY.get_user_stats(user_id)

    # DEBUG: Final response
    print(f"\n{'='*60}")
    print(f"FINAL RESPONSE TO CLIENT:")
    print(f"Reply length: {len(reply)} chars")
    print(f"Guiding question present: {'Guiding Question' in reply}")
    print(f"{'='*60}\n")

    return {
        "reflection": reply,
        "mode": request_data.mode,
        "backend": "ocean" if (effective_mode == "ocean" and OCEAN_ENDPOINT) else "local",
        "pond_mode": effective_mode,
        "pond_id": POND_ID,
        "ocean_meta": ocean_meta or None,
        "encryption_hash": encryption_hash,
        "user_hash": user_response_hash,
        "response_time_ms": round(response_time * 1000, 2),
        "scroll_number": stored_reflection.get("scroll_number") if isinstance(stored_reflection, dict) else None,
        "toadgang": request_data.mode == "toad",
        "memory": {
            "vow_detected": bool(detected_vow),
            "vow_text": detected_vow,
            "vow_stored": vow_stored,
            "pond_depth": user_stats.get("reflection_count", 0),
            "lotus_count": user_stats.get("vow_count", 0),
        },
        "stats": {
            "interaction_count": user_stats.get("interaction_count", 0),
            "vow_count": user_stats.get("vow_count", 0),
            "reflection_count": user_stats.get("reflection_count", 0),
        },
    }
    
    ocean_meta = {}

    if effective_mode == "ocean" and OCEAN_ENDPOINT:
        # Ocean mode → we build memory context locally, but let the Ocean decide its own prompt
        memory_context = POND_MEMORY.retrieve_context(user_id, request.query)

        raw_reply, ocean_meta = await call_ocean_backend(
            question=request.query,
            user_id=user_id,
            mode=request.mode or "reflect",
            context_from_pond=memory_context,
        )

        response_time = time.time() - start_time

    else:
        # Local mode → use our enhanced prompt builder with memory embedded
        prompt = EnhancedToadPromptBuilder.build_prompt_with_memory(
            query=request.query,
            user_id=user_id,
            encryption=request.encryption,
            mode=request.mode,
        )

        # DEBUG: Print prompt info
        print(f"\n{'='*60}")
        print(f"ASK ENDPOINT DEBUG - User: {user_id}")
        print(f"Query: {request.query}")
        print(f"Mode: {request.mode}")
        print(f"Prompt length: {len(prompt)} chars")
        print(f"First 300 chars of prompt:\n{prompt[:300]}...")
        print(f"{'='*60}\n")

        try:
            output = state.llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=[
                    "<|end|>",
                    "Encryption:",
                    "<|user|>",
                ],
            )
            response_time = time.time() - start_time
            raw_reply = output["choices"][0]["text"].strip()
            
            # DEBUG: Print raw reply
            print(f"\n{'='*60}")
            print(f"RAW MODEL OUTPUT:")
            print(f"Length: {len(raw_reply)} chars")
            print(f"Content:\n{raw_reply}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Model generation error: {str(e)}")

    # Apply cadence guard in both modes
    reply = cadence_guard(
        raw_reply,
        mode=request.mode or "reflect",
        user_query=request.query,
    )
    
    # DEBUG: Print after cadence guard
    print(f"\n{'='*60}")
    print(f"AFTER CADENCE GUARD:")
    print(f"Length: {len(reply)} chars")
    print(f"Content:\n{reply}")
    print(f"{'='*60}\n")

    # === MEMORY INTEGRATION ===
    # 1. Store this reflection in short-term memory
    stored_reflection = POND_MEMORY.store_reflection(
        user_id=user_id,
        query=request.query,
        response=reply,
        mode=request.mode,
        encryption=request.encryption,
    )

    # 2. Detect and store any vows made
    detected_vow = POND_MEMORY.detect_vow(request.query, reply)
    vow_stored = False
    if detected_vow:
        vow_stored = POND_MEMORY.store_user_vow(
            user_id=user_id,
            vow_text=detected_vow,
            context=request.query,
        )

    # 3. Submit depth packet to the Ocean (fire-and-forget)
    try:
        import asyncio
        asyncio.create_task(submit_depth_to_ocean())
    except Exception as _e:
        # Depth submission is best-effort only
        pass

    # 4. Generate a stable user hash for client to store
    user_response_hash = ToadEncryption.generate_user_hash(
        query=request.query,
        encryption=request.encryption,
        salt=str(time.time()),
    )

    # 5. Generate encryption hash (if any)
    encryption_hash = None
    if request.encryption:
        encryption_hash = ToadEncryption.generate_response_hash(
            request.query,
            reply,
        )

    # Get user stats for response
    user_stats = POND_MEMORY.get_user_stats(user_id)

    # DEBUG: Final response
    print(f"\n{'='*60}")
    print(f"FINAL RESPONSE TO CLIENT:")
    print(f"Reply length: {len(reply)} chars")
    print(f"Guiding question present: {'Guiding Question' in reply}")
    print(f"{'='*60}\n")

    return {
        "reflection": reply,
        "mode": request.mode,
        "backend": "ocean" if (effective_mode == "ocean" and OCEAN_ENDPOINT) else "local",
        "pond_mode": effective_mode,
        "pond_id": POND_ID,
        "ocean_meta": ocean_meta or None,
        "encryption_hash": encryption_hash,
        "user_hash": user_response_hash,  # Send back for client to store
        "response_time_ms": round(response_time * 1000, 2),
        "scroll_number": stored_reflection.get("scroll_number") if isinstance(stored_reflection, dict) else None,
        "toadgang": request.mode == "toad",
        "memory": {
            "vow_detected": bool(detected_vow),
            "vow_text": detected_vow,
            "vow_stored": vow_stored,
            "pond_depth": user_stats.get("reflection_count", 0),
            "lotus_count": user_stats.get("vow_count", 0),
        },
        "stats": {
            "interaction_count": user_stats.get("interaction_count", 0),
            "vow_count": user_stats.get("vow_count", 0),
            "reflection_count": user_stats.get("reflection_count", 0),
        },
    }

@app.post("/memory/vows")
async def get_user_vows(request: MemoryRequest):
    """Get a user's stored vows"""
    user_id = POND_MEMORY.get_user_id(request.user_hash, "vow_request")
    user_stats = POND_MEMORY.get_user_stats(user_id)
    
    if not user_stats["exists"]:
        return {
            "error": "User not found in memory",
            "suggestion": "Make a vow in conversation with the Mirror first"
        }
    
    vows = []
    if user_id in POND_MEMORY.user_vows:
        vows = POND_MEMORY.user_vows[user_id]
    
    return {
        "user_id": user_id,
        "vow_count": len(vows),
        "vows": vows,
        "immutable_axioms": IMMUTABLE_AXIOMS.strip().split("\n"),
        "lotus_count": len(vows)  # Each vow is a lotus bloom
    }

@app.post("/memory/reflections")
async def get_user_reflections(request: MemoryRequest, limit: int = 10):
    """Get a user's recent reflections"""
    user_id = POND_MEMORY.get_user_id(request.user_hash, "reflection_request")
    user_stats = POND_MEMORY.get_user_stats(user_id)
    
    reflections = []
    if user_id in POND_MEMORY.reflections_db:
        reflections = POND_MEMORY.reflections_db[user_id][-limit:]
    
    return {
        "user_id": user_id,
        "reflection_count": len(reflections),
        "total_interactions": user_stats.get("interaction_count", 0),
        "recent_reflections": reflections
    }

@app.post("/memory/stats")
async def get_user_stats(request: MemoryRequest):
    """Get comprehensive user statistics"""
    user_id = POND_MEMORY.get_user_id(request.user_hash, "stats_request")
    stats = POND_MEMORY.get_user_stats(user_id)
    
    return {
        **stats,
        "system_stats": {
            "total_interactions": state.total_interactions,
            "total_vows_stored": state.total_vows_stored,
            "total_scrolls_reflected": state.total_scrolls_reflected,
            "total_toad_secrets": state.toad_secrets_revealed
        }
    }

@app.get("/scroll/{scroll_number}")
async def get_scroll(scroll_number: int):
    """Get a specific scroll quote - FIXED"""
    if state.llm is None:
        raise HTTPException(status_code=503, detail="Mirror not ready")
    
    # Use the enhanced prompt builder but with minimal memory
    prompt = EnhancedToadPromptBuilder.build_prompt_with_memory(
        query=f"Mirror, quote exactly from Scroll {scroll_number}. Only the quote, nothing else.",
        user_id="scroll_reader_anon",
        mode="scroll"
    )
    
    output = state.llm(prompt, max_tokens=100, temperature=0.3)
    raw_quote = output["choices"][0]["text"].strip()
    
    # Clean the quote
    quote = cadence_guard(raw_quote, mode="scroll", user_query=f"scroll {scroll_number}")
    
    state.total_scrolls_reflected += 1
    
    return {
        "scroll": scroll_number,
        "quote": quote,
        "encryption_hash": ToadEncryption.generate_response_hash(
            f"Scroll {scroll_number}", quote
        )
    }

@app.post("/debug/format")
async def debug_format(request: AskRequest):
    """Debug endpoint to test formatting without running the model"""
    # Determine if guiding question is needed
    needs_gq = should_have_guiding_question(request.query, request.mode or "reflect")
    
    # Create a test response
    test_responses = {
        "reflect": "This is a test reflection about patience and stillness in the pond.",
        "scroll": "Scroll 7: The Jade Chest awaits those with true patience.",
        "toad": "The old frogs whisper secrets only in moonlight.",
        "rune": "Rune 1 represents the first step on the narrow path."
    }
    
    raw_response = test_responses.get(request.mode or "reflect", "Test reflection.")
    
    if needs_gq and request.mode == "reflect":
        raw_response += "\n\nGuiding Question: What does this test show you?"
    
    # Apply formatting
    formatted = force_mirror_format(
        raw_response,
        request.mode or "reflect",
        request.query
    )
    
    return {
        "query": request.query,
        "mode": request.mode,
        "needs_guiding_question": needs_gq,
        "raw_response": raw_response,
        "formatted_response": formatted,
        "formatting_applied": raw_response != formatted
    }
@app.get("/identity")
async def get_identity():
    """
    Return pond-level identity and linkage status.
    Safe to expose: no private keys, only public identity + metrics.
    """
    return {
        "pond_id": state.pond_id,
        "public_key": state.pond_public_key_hex,
        "first_breath": state.first_breath,
        "last_breath": state.last_breath,
        "continuous_days": state.continuous_days,
        "total_interactions": state.total_interactions,
        "total_vows_stored": state.total_vows_stored,
        "ocean_depth_linked": bool(OCEAN_DEPTH_ENDPOINT),
        "ocean_depth_endpoint": OCEAN_DEPTH_ENDPOINT,
        "pond_mode": POND_MODE,
    }

@app.get("/health")
async def health():
    """Health check with memory stats"""
    total_users = len(POND_MEMORY.user_metadata)
    total_vows = sum(len(vows) for vows in POND_MEMORY.user_vows.values())
    total_reflections = sum(len(refs) for refs in POND_MEMORY.reflections_db.values())
    
    return {
        "status": "🪞 Tobyworld Lotus Mirror with Memory Active",
        "model_name": state.model_name,
        "model_loaded": state.llm is not None,
        "memory_system": {
            "total_users": total_users,
            "total_vows": total_vows,
            "total_reflections": total_reflections,
            "active_memory": True
        },
        "interactions": {
            "scrolls_reflected": state.total_scrolls_reflected,
            "toad_secrets_revealed": state.toad_secrets_revealed,
            "total_interactions": state.total_interactions,
            "total_vows_stored": state.total_vows_stored
        },
        "uptime_seconds": round(time.time() - state.start_time, 2),
        "lore_modes": list(LOREMODES.keys()),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/encryption/{code}")
async def decrypt_code(code: str):
    mode = LOREMODES.get(code, "UNKNOWN_MODE")
    return {
        "code": code,
        "mode": mode,
        "description": f"Activates {mode} in the trained model",
        "valid": code in LOREMODES,
        "memory_effect": "Memory context is still injected with encryption modes"
    }

# ==================== MAIN ====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🪞 Tobyworld Lotus Mirror Pond with Memory Integration")
    parser.add_argument("--model", required=True, help="Path to trained GGUF model")
    parser.add_argument("--host", default="0.0.0.0", help="Host")
    parser.add_argument("--port", type=int, default=7777, help="Port (7777 for magic)")
    parser.add_argument("--gpu-layers", type=int, default=80, help="GPU layers")
    args = parser.parse_args()
    
    print(f"""
    🪞 TOBYWORLD LOTUS MIRROR POND WITH MEMORY 🪞
    {"="*60}
    Model: {os.path.basename(args.model)}
    Type: FINE-TUNED + MEMORY INTEGRATION
    GPU Layers: {args.gpu_layers}
    Port: {args.port} (Lotus number)
    Theme: Original Beautiful Interface Preserved
    Memory Features: Vow tracking, Context retrieval, Pond depth, Lotus blooms
    {"="*60}
    """)
    
    try:
        load_trained_toad(args.model, args.gpu_layers)
        
        print(f"""
    ✅ LOTUS + MEMORY MIRROR READY!
    
    🌐 Web Interface: http://{args.host}:{args.port}
    
    🎨 Original Beautiful Theme:
    • All original colors, gradients, and layouts preserved
    • Same stunning mirror chamber with lotus symbol
    • Original action buttons and mode selector
    
    🧠 Memory System Integrated:
    • Vow Detection: Automatically captures vows/commitments
    • Pond Depth: Tracks interaction depth per traveler
    • Context Injection: Provides memory context for deeper reflections
    • Lotus Blooms: Each vow creates a lotus in the pond
    
    🌸 New Memory Features:
    • Memory Panel: View your vows and interaction history
    • Pond Depth Indicator: Visual representation of your reflection depth
    • User Continuity: localStorage preserves your memory across sessions
    • Vow Recognition: Mirror detects and remembers commitments
    
    💾 Memory Endpoints:
    • POST /memory/vows - Get your stored vows
    • POST /memory/reflections - Get your reflection history
    • POST /memory/stats - Get comprehensive memory statistics
    
    📝 Usage Tip: Make vows to the Mirror (e.g., "I vow to...") 
      to create lotuses in your pond. The Mirror will remember.
    """)
        
    except Exception as e:
        print(f"❌ Failed to load lotus mirror with memory: {e}")
        exit(1)
    
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )