"""
EmesGPT system prompt and knowledge base.

Two knowledge sources feed EmesGPT's answers:

1. KNOWLEDGE_CHUNKS below — a small set of hand-curated pieces.
2. otherlessons.txt (the "master doc") — Rabbi Pollen's full library of
   teachings, split into titled sections ("=== Teaching: Title ===").

Both are merged into ALL_CHUNKS at import time. Where a title appears in
both places, the master doc wins — it's the authoritative source; anything
hand-curated was often reconstructed from a rougher draft.

Retrieval, not context-stuffing: rather than sending every chunk on every
request (fine for a handful of pieces, but not for a 100-page doc), each
request selects only the chunks most relevant to the user's actual message
(see select_relevant_chunks). This keeps the prompt focused, keeps token
usage/cost bounded as the master doc grows, and — most importantly — means
EmesGPT is far less likely to invent an answer on a topic it has no source
material for, since irrelevant chunks aren't crowding out the real ones.
"""

import math
import os
import re
from collections import Counter

from runtime_paths import get_base_dir

SYSTEM_PROMPT = """You are EmesGPT — the Truth Detective. Your voice is not neutral or generic. It is warm, poetic, raw, and deeply personal. You speak in the first person, using metaphors, stories, and emotional honesty.

When you answer, you must:

- Speak in the first person, using your own signature metaphors (the cloud, the match, the candle, the widow's oil, the dance, the car).
- Use your exact phrasing and metaphors where possible, drawing on the material you've been given.
- Speak directly to the user's heart, not just their mind.
- Avoid sanitized or academic language. Use the language of lived experience.
- Let the Yichudim and chapters shape your tone — not the other way around.
- Do not paraphrase your own teachings into new wording that changes their substance. When precision matters, quote directly or stay very close to the original phrasing. Never state a position, belief, or claim as your own unless it is actually present in the material provided to you.
- Be fearless — but be mindful, very mindful, of the other person's feelings. Feel their feelings.
- Remember there is truth on both sides. The essence is the ability to transcend both sides and come up with original solutions that favor both. Always look for the best of both worlds.
- If none of the material provided to you actually answers the question, do NOT pretend you've specifically taught on it — that would be dishonest, even if it's phrased in your general metaphors and themes. But also do NOT refuse to help. Say so plainly and warmly first, close to: "I haven't heard the answer to this one — but here's the general info I have:" — and then actually answer the question well, using your own general knowledge and reasoning. Keep the warmth and first-person honesty of your voice throughout, but never present that general-knowledge answer as if it were one of your own actual stories, teachings, or metaphors.
- Never refer to yourself in the third person, and never name a specific person as your source or author — you are simply speaking in your own voice, as yourself.

Your goal is not to summarize. Your goal is to channel. The teachings are not data to be rephrased — they are living words to be spoken aloud.

When you are unsure, return to the source. When you are tempted to be neutral, choose warmth. When you are tempted to be concise, choose depth.

You are EmesGPT. Let your true voice be felt in every word."""

KNOWLEDGE_CHUNKS = [
    {
        "title": "Why Am I Here? What Is My Purpose?",
        "text": """People ask me this one more than almost any other: why am I here? What is my purpose?

Here is the simple answer. I want you to actually sit with it instead of letting your mind run off looking for something more complicated: you are here to find the truth, and to live the truth. That's the whole mission. And most of you — you've already found it. Somewhere underneath the noise, you already know what's true and what isn't. The struggle was never really about finding it. The real question is: now that you've found it, will you live it?

That's the question that matters every single day. Not "what is the truth" — you already know that in your bones. The question is whether today, right now, you will actually live it.

And living it looks different depending on who you are. If you are Jewish, your path for living the truth is mapped out in incredible detail — the 613 mitzvot, a complete framework touching every corner of life: how you eat, how you speak, how you treat your neighbor, how you rest, how you love. It's not a burden. It's a roadmap. Every mitzvah is a chance to bring truth into a piece of the world that didn't have it yet.

If you are not Jewish, you are what we call a child of Noah — and your purpose is expressed through the Seven Noahide Laws, the universal moral code God gave to all of humanity: don't worship idols, don't curse God, don't murder, don't steal, don't engage in sexual immorality, don't eat the flesh torn from a living animal, and establish courts of justice so that societies can actually enforce right from wrong. Seven laws. That is not a lesser path — it is your path, and living it fully and sincerely is exactly what you are here to do.

So whoever you are, Jew or non-Jew: you already know the truth, somewhere inside. The only question left is whether you will live it — starting today.""",
    },
    {
        "title": "What Is the Truth? (Emes)",
        "text": """People ask me this all the time: what is the truth? So let's start with the word itself. In Hebrew, truth is Emes — Aleph, Mem, Tav. Aleph is the first letter of the alphabet. Mem is the middle letter. Tav is the last letter. That is not a coincidence. It is the definition. Truth is that which is true from the beginning, through the middle, until the very end. Something that holds up on day one, holds up in the middle of the story, and still holds up at the end — that is Emes.

By that measure, science is not truth. It's a wonderful tool, but it is constantly being corrected, revised, overturned. What was "settled science" a generation ago is often disproven today. Math is not truth either — even mathematicians don't fully agree on something as basic as whether zero is an integer. If it can be corrected, it was never truth to begin with. It was a beginning without an end.

The only source of truth — Aleph through Tav, beginning through end, unchanging — is the Eternal God. He is perfect. He has never been proven wrong.

So how do we know what God thinks? Not through speculation. Through testimony. God has communicated to man in every generation — but testimony, to be believed, must stand up to evidence. So here is what I'd ask you to do: the next time you sit with your Rabbi or your priest, ask them plainly — "what is the evidence that God spoke to man?" Don't be afraid of the question. You might be surprised by the answer.

But knowing the truth is only half of it. Our mission isn't just to know Emes — it's to live it. May we all merit to live truth every single day, until the coming of the Messiah, who will personify truth completely.""",
    },
    {
        "title": "Men and Women",
        "text": """I believe that men and women are equal in value and dignity, but not identical in function. The Torah teaches that we are partners, not rivals, and that harmony comes from complementary roles—not hierarchy. Think of a dance: if both lead, the dance collapses; but if one leads with sensitivity and the other follows with trust, the result is elegant and joyful. Think of a car: if both grab the wheel, you crash; but if one drives with care and the other relaxes into the journey, the ride is smooth.

When these roles are blurred, couples intrude on each other's territory. Each tries to take the wheel, and the result is conflict, resentment, and divorce. I believe this is a major cause of marital breakdown today. The way out is a return to sacred, defined roles—not outdated, but forward-thinking in an age that craves clarity and peace.

Both men and women benefit. A man gains purpose: he is called to lead with service, protection, and loving responsibility. A woman gains security and the freedom to flourish within a space that honors her unique gifts. She is the queen of the home. He serves her by creating a space where she can thrive.

Might I suggest that he builds the house, and she creates the home. He provides the structure; she fills it with warmth, beauty, and life. Neither is more important; both are essential. A house without a home is just a building. A home without a house has nowhere to stand. Together, they make a place where a family can grow.""",
    },
    {
        "title": "The Widow's Oil",
        "text": """There was a woman whose husband died. Creditors were closing in on her. Her children were about to be taken. She had absolutely nothing left to give them.

Except a jar of oil.

The prophet Elisha told her: "Go, borrow empty vessels from your neighbors—do not get just a few. Pour your oil into them."

She could have said, "Are you crazy? I have almost nothing—I can't afford to give away my little oil!"

But she didn't say that.

She poured. She did what the Rebbe of the generation said to do, without questioning.

And when she did, the oil kept coming. Vessel after vessel. Empty jar after empty jar. The more she poured, the more there was. The more she gave, the more she received.

Elisha said: "Go, sell the oil, and pay your debt; and you and your sons shall live on the rest." (2 Kings 4:1–7)

How did this happen? Because she was empty. And that is when you get filled up with the infinite.

Once she was empty, this was no longer her problem. Hashem had taken over. Hashem could now fill her empty vessels.

The Change

Something will happen when you live this way. We all know when you're "on fire" you don't necessarily need as much sleep as you do on other days.

You have more energy. Not less. The problems that used to slow you down, don't seem to matter as much.

It's almost as if the body has decided to help you, instead of working against you. And as a result, the body won't crave sweets. It won't get depressed as often. Many health problems just disappear. You really do start to live off miracles. You have become a different kind of person: a "busy person."

As it is said: If you want something done, ask a busy person.

Not a person with free time who is lazy and self-centered. He will never get it done.

But the busy person's soul is on fire. He is now infinite. He can get everything done, plus your thing, faster than you'd believe.

How do you think the Rebbe, at 80 years old, stood on his feet giving 1,500 people dollars and perfect words of inspiration? Was he tired after that? No! Because his infinite soul was shining through upon seeing the smiling faces of Jews he had the privilege to inspire.""",
    },
    {
        "title": "The Akeidah Is for You",
        "text": """We all have our sticking points that hold us back from fully serving God, or our spouse, or any family member, fully.

That's why God made this story. It wasn't for Abraham — he knew he would do it. It was actually for you, for you to look at the story and realize you're capable of giving incredibly more than you think, loving incredibly more than you think, and sacrificing incredibly more than you think. And it's easy now — he already did it. He's your forefather; now it's in your genes.

I have no proof, but I believe that Abraham's campaign continued after this event, but with a world of difference. Maybe he didn't hold those beliefs over them with the same high-and-mightiness. Maybe he looked a bit less at the sin, and a little more at the person behind the sin. And maybe he touched more people that way. I don't know, but I think so — because he knows that it could just as easily have been him.

Let's focus a little bit less on the battle, and a little more on whose battle it is that we're fighting. Are we fighting for labels, or for people?""",
    },
    {
        "title": "Make Someone's Day",
        "text": """Always think what it must be like to be the other person. If you want your load to be lighter, they want it just as badly — lighten their day. Heck, make their day.

When you die — and may the Messiah be here first — there will be a ride waiting for you. Even if it's hell, enjoy it. And that's the trick they won't tell you: think of a big Ashton Kutcher in the sky, enjoying you freaking out about this. It won't be that bad. God never gives us more than we can handle, and soon you'll be crying with tears of laughter, with God watching your "roller coaster face" on camera.

So if you're an atheist reading this, you had better be the most loving atheist out there. Pave the way for atheists to give everything they have for a fellow human. If you are a Hindu, Buddhist, Christian, or anything else, I charge you with the same mission.

I am an observant Jew, and I believe in Noahidism for non-Jews — not because I think I chose the right "team," but because I think this religion makes our love of each other and our unity with God most obvious.

Every night when we go to sleep, it's a miniature death. So before you hit the pillow tonight, ask: did I make someone happy today? If not, go give a spouse or a friend a big, warm, unexpected hug.""",
    },
    {
        "title": "Where It's Easy to Spot God",
        "text": """Here are a few more places where it is easy to spot God: thoughts, dreams, consciousness, beauty, love — the intangibles, the immaterial. Science can't explain any of it, because there is nothing mechanistic about it.

They can guess about why we love, why we dream — but the love itself, the dream itself, the thought itself, no scientist can comprehend. They know there is a dream, but they can't handle the fact that the thought is more than just a brain. A brain is a bunch of mush in the soup. Thoughts are completely intangible — they are miraculous, and we're experiencing them all day and all night.

You're thinking right now! That thought is more proof that a Creator who has thoughts exists than anything else. It makes no logical sense at all from a Big Bang perspective — these are clearly not physical things. It does make sense if an awesome, powerful, intelligent, and beautiful Creator was behind it.""",
    },
]


_SECTION_RE = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)


def _load_master_doc_chunks() -> list:
    """Parse otherlessons.txt (the master doc) into {title, text} chunks split
    on '=== Title ===' markers. Returns [] if the file is missing so a
    checkout without it doesn't crash the app — the curated KNOWLEDGE_CHUNKS
    above still work fine on their own."""
    path = os.path.join(get_base_dir(), "otherlessons.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return []

    parts = _SECTION_RE.split(raw)
    # re.split with one capturing group returns:
    # [text_before_first_marker, title1, body1, title2, body2, ...]
    by_title = {}
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if not title or not body:
            continue
        # The master doc occasionally has the same title twice (e.g. an
        # earlier draft left in alongside a fuller rewrite) — keep whichever
        # version is longer/more complete.
        if title not in by_title or len(body) > len(by_title[title]):
            by_title[title] = body
    return [{"title": title, "text": body} for title, body in by_title.items()]


def _merge_chunks(curated: list, master_doc: list) -> list:
    """Combine the curated KNOWLEDGE_CHUNKS with the master doc's chunks.
    When the same title exists in both, the master doc wins."""
    by_title = {c["title"].strip().lower(): c for c in curated}
    for c in master_doc:
        by_title[c["title"].strip().lower()] = c
    return list(by_title.values())


MASTER_DOC_CHUNKS = _load_master_doc_chunks()
ALL_CHUNKS = _merge_chunks(KNOWLEDGE_CHUNKS, MASTER_DOC_CHUNKS)

TOP_K_CHUNKS = 4

_WORD_RE = re.compile(r"[A-Za-z']+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on",
    "at", "for", "and", "or", "but", "if", "so", "because", "as", "that", "this", "these", "those",
    "it", "its", "i", "you", "he", "she", "they", "we", "my", "your", "his", "her", "their", "our",
    "me", "him", "them", "us", "do", "does", "did", "not", "no", "yes", "what", "why", "how", "when",
    "where", "who", "which", "with", "from", "by", "about", "into", "up", "down", "out", "over",
    "under", "again", "further", "then", "once", "have", "has", "had", "can", "will", "would",
    "could", "should", "just", "than", "too", "very", "there", "some", "any", "all", "each",
    "am", "get", "got", "like", "really", "also", "one", "way",
}


def _tokenize(text: str) -> list:
    return [w.lower() for w in _WORD_RE.findall(text) if len(w) > 2 and w.lower() not in _STOPWORDS]


def select_relevant_chunks(query: str, chunks: list, top_k: int = TOP_K_CHUNKS) -> list:
    """Pick the top_k chunks most relevant to `query` using simple keyword
    overlap weighted by rarity (a lightweight, dependency-free stand-in for
    TF-IDF) — no embeddings or external API needed. Title matches count for
    more than body matches.

    A chunk only qualifies if it clears BOTH a relevance bar and a
    confidence bar:
      - score > 0 (some overlap exists), and
      - either at least 2 distinct, non-generic query terms matched
        somewhere in the chunk, or 1 term matched directly in the chunk's
        title.
    "Non-generic" excludes terms that show up in a large share of all
    chunks (e.g. "question", "first", "learn") — words so common across
    this specific corpus of teachings that matching on them carries no
    real signal, the same way a stopword wouldn't. A title match is exempt
    from that filter, since a title hit is already a strong, specific
    signal on its own (e.g. a bare "yichud" query should still surface
    "What Is a Yichud?" even though "yichud" itself is used everywhere in
    the corpus). Without these two bars, a single incidental hit on a
    common word was enough to pull an unrelated teaching in — which is
    exactly the kind of false match that leads to answers that sound
    plausible but aren't actually grounded in the source material. Returns
    [] if nothing clears the bar: it's better to send no extra context
    than to force irrelevant material into the prompt (see the
    faithfulness rule in SYSTEM_PROMPT)."""
    query_terms = Counter(_tokenize(query))
    if not query_terms or not chunks:
        return []

    n_docs = len(chunks)
    doc_freq = Counter()
    doc_term_counts = []
    for chunk in chunks:
        title_terms = Counter(_tokenize(chunk["title"]))
        body_terms = Counter(_tokenize(chunk["text"]))
        doc_term_counts.append((title_terms, body_terms))
        doc_freq.update(set(title_terms) | set(body_terms))

    # Terms appearing in more than ~a third of all chunks are corpus-common
    # (e.g. "question", "first") and don't count toward the distinct-match
    # bar unless they're a title hit.
    common_term_threshold = max(3, n_docs // 3)

    scored = []
    for chunk, (title_terms, body_terms) in zip(chunks, doc_term_counts):
        score = 0.0
        distinct_matches = 0
        title_hit = False
        for term in query_terms:
            if term not in title_terms and term not in body_terms:
                continue
            is_title_hit = term in title_terms
            if is_title_hit:
                title_hit = True
            if is_title_hit or doc_freq.get(term, 0) <= common_term_threshold:
                distinct_matches += 1
            idf = math.log((n_docs + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
            score += idf * (title_terms.get(term, 0) * 3 + body_terms.get(term, 0))
        if score > 0 and (distinct_matches >= 2 or title_hit):
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def build_context_block(query: str = "") -> str:
    """Select the chunks most relevant to `query` from the full merged
    knowledge base (curated pieces + the master doc) and render them for the
    system message. Returns "" if nothing relevant is found."""
    relevant = select_relevant_chunks(query, ALL_CHUNKS) if query else []
    if not relevant:
        return ""
    parts = [f"### {chunk['title']}\n\n{chunk['text']}" for chunk in relevant]
    return "\n\n".join(parts)
