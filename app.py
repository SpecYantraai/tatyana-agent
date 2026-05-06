"""
Tatyana's Content Agent — Production v2
Full learning engine: ratings + edit distance + deletion patterns
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='.')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tatyana_kb.json')
with open(KB_PATH, 'r', encoding='utf-8') as f:
    KB = json.load(f)


# ── Helpers ───────────────────────────────────────────────
def data_path(name):
    if not name.endswith('.json'):
        name += '.json'
    return os.path.join(DATA_DIR, os.path.basename(name))


def read_json(name, default=None):
    path = data_path(name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default if default is not None else {}


def write_json(name, data):
    with open(data_path(name), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def edit_distance_ratio(original, edited):
    """Simple similarity ratio — 1.0 = identical, 0.0 = completely different"""
    if not original or not edited:
        return 0.0
    orig_words = set(original.lower().split())
    edit_words = set(edited.lower().split())
    if not orig_words:
        return 0.0
    intersection = orig_words & edit_words
    return len(intersection) / max(len(orig_words), len(edit_words))


# ── Learning Engine ───────────────────────────────────────
def build_learning_context():
    """Dynamically builds learning context from all feedback signals"""
    memory = read_json('memory', {'entries': []})
    entries = memory.get('entries', [])

    if len(entries) < 3:
        return ""  # Not enough data yet

    # Signal 1: Format ratings
    format_scores = {}
    format_counts = {}
    for e in entries:
        fmt = e.get('format', 'unknown')
        rating = e.get('rating')
        if rating:
            format_scores[fmt] = format_scores.get(fmt, 0) + rating
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

    format_avgs = {
        fmt: round(format_scores[fmt] / format_counts[fmt], 1)
        for fmt in format_scores if format_counts[fmt] >= 2
    }

    high_formats = [f for f, s in format_avgs.items() if s >= 4.0]
    low_formats = [f for f, s in format_avgs.items() if s <= 2.5]

    # Signal 2: Edit patterns — what she consistently adds/removes
    edit_patterns = []
    low_edit_distance = []
    high_edit_distance = []

    for e in entries:
        original = e.get('original_text', '')
        final = e.get('final_text', '')
        if original and final:
            ratio = edit_distance_ratio(original, final)
            if ratio > 0.85:
                low_edit_distance.append(e.get('format', ''))
            elif ratio < 0.5:
                high_edit_distance.append(e.get('format', ''))

    # Signal 3: Deleted posts (implicit rejection)
    deleted = read_json('deleted', {'entries': []})
    deleted_formats = {}
    for d in deleted.get('entries', []):
        fmt = d.get('format', 'unknown')
        deleted_formats[fmt] = deleted_formats.get(fmt, 0) + 1

    avoided_formats = [f for f, c in deleted_formats.items() if c >= 2]

    # Signal 4: Phrases she keeps vs removes
    kept_phrases = []
    removed_phrases = []
    kb_phrases = KB['voice']['signature_phrases']
    for e in entries:
        final = e.get('final_text', '')
        if final:
            for phrase in kb_phrases:
                short = phrase[:30]
                if short.lower() in final.lower():
                    kept_phrases.append(short)

    # Build context string
    context_parts = []

    if high_formats:
        context_parts.append(f"FORMATS THAT WORK WELL FOR HER (use these): {', '.join(high_formats)}")

    if low_formats:
        context_parts.append(f"FORMATS SHE RATES LOW (avoid): {', '.join(low_formats)}")

    if avoided_formats:
        context_parts.append(f"FORMATS SHE DELETES WITHOUT USING (never use): {', '.join(avoided_formats)}")

    if low_edit_distance:
        context_parts.append(f"FORMATS WHERE SHE BARELY EDITS (agent is calibrated here): {', '.join(set(low_edit_distance))}")

    if high_edit_distance:
        context_parts.append(f"FORMATS SHE HEAVILY REWRITES (agent needs improvement here): {', '.join(set(high_edit_distance))}")

    if kept_phrases:
        from collections import Counter
        most_kept = [p for p, c in Counter(kept_phrases).most_common(3)]
        context_parts.append(f"PHRASES SHE CONSISTENTLY KEEPS: {', '.join(most_kept)}")

    if not context_parts:
        return ""

    return "\n=== LEARNED FROM HER BEHAVIOUR ===\n" + "\n".join(context_parts) + "\n"


def build_voice_context():
    kb = KB
    learning = build_learning_context()

    return f"""
YOU ARE WRITING FOR: Tatyana Arbouzova
Role: Quality Leader of the Year 2026, Director of Quality Engineering at ContextQA, 
      Podcast Host (The Agentic Quality Podcast), Innovate QA Conference Organizer
Audience: QA engineers, SDETs, engineering leaders — 14,471 LinkedIn followers

VOICE AND TONE:
{kb['voice']['tone']}
{kb['voice']['personality']}

HER SIGNATURE PHRASES (use naturally, not forced):
{chr(10).join('- ' + p for p in kb['voice']['signature_phrases'])}

OPENER STYLES SHE USES:
{chr(10).join('- ' + s for s in kb['voice']['opener_styles'])}

NEVER WRITE:
{chr(10).join('- ' + n for n in kb['voice']['never'])}

HER CONTENT PILLARS:
{chr(10).join('- ' + p for p in kb['content_pillars'])}

REAL EXAMPLES FROM HER POSTS (match this energy exactly):
{chr(10).join(f'[{e["format"]}] {e["post"][:300]}' for e in kb['few_shot_examples'])}

{learning}

CRITICAL RULES:
- Short paragraphs, maximum 3 lines each
- Direct, no fluff, no corporate speak
- End with a question that drives comments
- Sound like a 26-year veteran who has seen everything and still cares deeply
- NOT like an AI content generator
"""


# ── Static ────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# ── Data API ──────────────────────────────────────────────
@app.route('/data/<filename>', methods=['GET'])
def get_data(filename):
    return jsonify(read_json(filename, {}))


@app.route('/data/<filename>', methods=['POST'])
def set_data(filename):
    write_json(filename, request.json)
    return jsonify({'ok': True})


# ── LLM ──────────────────────────────────────────────────
def call_llm(prompt, provider, api_key, max_tokens=1500):
    if provider == 'openai':
        body = json.dumps({
            'model': 'gpt-4o',
            'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=body,
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data['choices'][0]['message']['content']

    elif provider == 'anthropic':
        body = json.dumps({
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01'
            }
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return data['content'][0]['text']

    raise ValueError(f'Unknown provider: {provider}')


def parse_json_response(text):
    clean = text.strip()
    if '```json' in clean:
        clean = clean.split('```json')[1].split('```')[0].strip()
    elif '```' in clean:
        clean = clean.split('```')[1].split('```')[0].strip()
    return json.loads(clean)


# ── Feature 1: Link → Post ────────────────────────────────
@app.route('/api/link-to-post', methods=['POST'])
def link_to_post():
    d = request.json
    url = d.get('url', '')
    context = d.get('context', '')
    provider = d.get('provider', 'openai')
    api_key = d.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API key required'}), 400

    voice = build_voice_context()

    prompt = f"""{voice}

TASK: Write 3 different LinkedIn posts for Tatyana sharing this content.

URL: {url}
Her notes on it: {context if context else 'No additional context provided'}

Write 3 posts using these 3 different formats:
1. SCENARIO/QUESTION format — open with a provocative question or cost scenario
2. PERSONAL TAKE format — open with her genuine reaction or observation  
3. COMMUNITY format — open with why her specific audience needs this

Each post:
- 3-5 short paragraphs
- Ends with a question to drive comments
- Include [LINK] where URL goes
- 3-5 hashtags at end

Return ONLY a JSON array of 3 objects with keys:
- format (string): name of the format used
- hook (string): the opening line only
- body (string): full post text including hook, include [LINK] and hashtags at end
- edit_hint (string): one sentence on what she might want to personalise

Return ONLY the JSON array. No markdown fences."""

    try:
        result = call_llm(prompt, provider, api_key)
        posts = parse_json_response(result)
        # Store originals for edit distance tracking
        for i, p in enumerate(posts):
            p['id'] = f"link_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
            p['original_text'] = p['body']
            p['source_url'] = url
            p['feature'] = 'link_post'
        return jsonify({'posts': posts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Feature 2: Event Content ──────────────────────────────
@app.route('/api/event-content', methods=['POST'])
def event_content():
    d = request.json
    provider = d.get('provider', 'openai')
    api_key = d.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API key required'}), 400

    voice = build_voice_context()

    # Check known events
    known_extra = ''
    for evt in KB['upcoming_events']:
        if evt['name'].lower() in d.get('event_name', '').lower():
            known_extra = f"This is HER OWN conference she organises. Hashtag: {evt['hashtag']}. Use this hashtag."
            break

    prompt = f"""{voice}

TASK: Generate a 5-post LinkedIn content sequence for this event.

Event: {d.get('event_name')}
Date: {d.get('event_date')}
Location: {d.get('event_location')}
URL: {d.get('event_url')}
Details: {d.get('details', '')}
{known_extra}

Generate exactly 5 posts:
1. ANNOUNCEMENT (2-3 weeks before) — build excitement, what makes this different
2. COUNTDOWN (1 week before) — speaker spotlight or key session preview  
3. DAY-OF ENERGY (morning of event) — live energy, FOMO for those not there
4. LIVE MOMENT (during event) — one key insight from the room
5. HONEST RECAP (day after) — real reflection, lessons, gratitude

Each post:
- Authentic Tatyana voice, 2-4 short paragraphs
- Ends with engagement question or CTA
- Relevant hashtags

Return ONLY a JSON array of 5 objects with keys:
- timing (string): when to post
- title (string): short label for this post
- body (string): full post text
- hashtags (array): list of hashtags
- tip (string): posting tip or personalisation suggestion

Return ONLY the JSON array. No markdown fences."""

    try:
        result = call_llm(prompt, provider, api_key)
        posts = parse_json_response(result)
        for i, p in enumerate(posts):
            p['id'] = f"event_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
            p['original_text'] = p['body']
            p['feature'] = 'event_post'
            p['format'] = p.get('title', 'Event Post')
        return jsonify({'sequence': posts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Feature 3: Podcast Repurposer ────────────────────────
@app.route('/api/podcast-repurpose', methods=['POST'])
def podcast_repurpose():
    d = request.json
    provider = d.get('provider', 'openai')
    api_key = d.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API key required'}), 400

    voice = build_voice_context()

    prompt = f"""{voice}

TASK: Repurpose this podcast episode into 5 LinkedIn posts.

Podcast: {KB['podcast']['name']}
Tagline: {KB['podcast']['tagline']}
Episode: {d.get('title')}
Guest: {d.get('guest')} — {d.get('guest_title')}
Episode URL: {d.get('url', '')}
Content/Summary: {d.get('content', 'No transcript provided — generate based on guest background and episode title')}

Generate 5 posts:
1. EPISODE LAUNCH — Drive listeners to the episode, why this guest matters
2. KEY INSIGHT — The most counterintuitive thing from the conversation
3. PULL QUOTE — Powerful thing the guest said (or would say)
4. PRACTICAL TAKEAWAY — What QA teams can do TODAY from this episode
5. COMMUNITY QUESTION — Big open question this episode raises

Each post: Tatyana's voice, 2-4 paragraphs, engagement hook at end.
Include [EPISODE_LINK] where relevant.

Return ONLY a JSON array of 5 objects with keys:
- type (string): post type label
- body (string): full post text
- hashtags (array): hashtags list
- best_time (string): best time to post this one

Return ONLY the JSON array. No markdown fences."""

    try:
        result = call_llm(prompt, provider, api_key)
        posts = parse_json_response(result)
        for i, p in enumerate(posts):
            p['id'] = f"pod_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
            p['original_text'] = p['body']
            p['feature'] = 'podcast_post'
            p['format'] = p.get('type', 'Podcast Post')
        return jsonify({'posts': posts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Learning: Save feedback ───────────────────────────────
@app.route('/api/feedback', methods=['POST'])
def save_feedback():
    """Save rating + edit distance — core learning signal"""
    d = request.json
    memory = read_json('memory', {'entries': []})

    entry = {
        'id': d.get('id', ''),
        'date': datetime.now().strftime('%b %d'),
        'timestamp': datetime.now().isoformat(),
        'feature': d.get('feature', ''),
        'format': d.get('format', ''),
        'source_url': d.get('source_url', ''),
        'original_text': d.get('original_text', ''),
        'final_text': d.get('final_text', ''),
        'edit_ratio': edit_distance_ratio(
            d.get('original_text', ''),
            d.get('final_text', '')
        ),
        'rating': d.get('rating', 0),
        'used': d.get('used', False),
        'preview': d.get('final_text', '')[:80]
    }

    entries = memory.get('entries', [])
    # Update if exists, else prepend
    existing_ids = [e.get('id') for e in entries]
    if entry['id'] in existing_ids:
        entries = [entry if e.get('id') == entry['id'] else e for e in entries]
    else:
        entries.insert(0, entry)

    entries = entries[:100]  # Keep last 100
    write_json('memory', {'entries': entries})
    return jsonify({'ok': True, 'edit_ratio': entry['edit_ratio']})


@app.route('/api/delete-feedback', methods=['POST'])
def delete_feedback():
    """Track deletions — implicit rejection signal"""
    d = request.json
    deleted = read_json('deleted', {'entries': []})
    deleted['entries'].insert(0, {
        'date': datetime.now().strftime('%b %d'),
        'format': d.get('format', ''),
        'feature': d.get('feature', ''),
        'preview': d.get('preview', '')[:60]
    })
    deleted['entries'] = deleted['entries'][:50]
    write_json('deleted', deleted)
    return jsonify({'ok': True})


@app.route('/api/insights', methods=['GET'])
def get_insights():
    """Return learning insights for the UI"""
    memory = read_json('memory', {'entries': []})
    entries = memory.get('entries', [])
    rated = [e for e in entries if e.get('rating')]

    if len(rated) < 3:
        return jsonify({
            'ready': False,
            'message': f'Rate {3 - len(rated)} more posts to unlock insights'
        })

    from collections import defaultdict
    format_data = defaultdict(list)
    for e in rated:
        format_data[e.get('format', 'Unknown')].append(e.get('rating', 0))

    formats = []
    for fmt, ratings in format_data.items():
        if len(ratings) >= 2:
            avg = sum(ratings) / len(ratings)
            formats.append({'format': fmt, 'avg': round(avg, 1), 'count': len(ratings)})

    formats.sort(key=lambda x: x['avg'], reverse=True)

    # Edit accuracy
    edit_data = [e for e in entries if e.get('edit_ratio') is not None]
    avg_edit = sum(e['edit_ratio'] for e in edit_data) / len(edit_data) if edit_data else 0

    return jsonify({
        'ready': True,
        'total_posts': len(entries),
        'total_rated': len(rated),
        'formats': formats,
        'avg_accuracy': round(avg_edit * 100),
        'best_format': formats[0]['format'] if formats else None,
        'worst_format': formats[-1]['format'] if len(formats) > 1 else None
    })


@app.route('/api/test-key', methods=['POST'])
def test_key():
    d = request.json
    try:
        call_llm("Say OK", d.get('provider'), d.get('api_key'), max_tokens=5)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5500))
    app.run(host='0.0.0.0', port=port, debug=False)
