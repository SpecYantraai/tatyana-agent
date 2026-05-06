"""
Tatyana's Content Agent — Production Server
Deployable to Railway. Mobile-first. All three features.
"""

import json
import os
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='.')

# Load Tatyana's KB
KB_PATH = os.path.join(os.path.dirname(__file__), 'tatyana_kb.json')
with open(KB_PATH, 'r') as f:
    KB = json.load(f)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)


# ── Static files ─────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# ── Data persistence ──────────────────────────────────────
@app.route('/data/<filename>', methods=['GET'])
def read_data(filename):
    filename = os.path.basename(filename)
    if not filename.endswith('.json'):
        filename += '.json'
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({})


@app.route('/data/<filename>', methods=['POST'])
def write_data(filename):
    filename = os.path.basename(filename)
    if not filename.endswith('.json'):
        filename += '.json'
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w') as f:
        json.dump(request.json, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True})


# ── LLM proxy ─────────────────────────────────────────────
def call_llm(prompt, provider, api_key, model=None):
    if provider == 'openai':
        body = json.dumps({
            'model': model or 'gpt-4o',
            'max_tokens': 1500,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=body,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data['choices'][0]['message']['content']

    elif provider == 'anthropic':
        body = json.dumps({
            'model': model or 'claude-sonnet-4-20250514',
            'max_tokens': 1500,
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
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        return data['content'][0]['text']

    raise ValueError(f'Unknown provider: {provider}')


def build_voice_context():
    kb = KB
    return f"""
TATYANA'S VOICE AND STYLE:
Tone: {kb['voice']['tone']}
Personality: {kb['voice']['personality']}

Signature phrases she actually uses (use these naturally):
{chr(10).join('- ' + p for p in kb['voice']['signature_phrases'])}

Opener styles:
{chr(10).join('- ' + s for s in kb['voice']['opener_styles'])}

NEVER write:
{chr(10).join('- ' + n for n in kb['voice']['never'])}

Her content pillars:
{chr(10).join('- ' + p for p in kb['content_pillars'])}

REAL EXAMPLES FROM HER POSTS (match this energy):
{chr(10).join(f'[{e["format"]}] "{e["post"][:200]}"' for e in kb['few_shot_examples'])}

Hashtags she uses: {' '.join(kb['hashtags']['always'][:3])} + topic-specific ones

CRITICAL: Write like a senior QA leader with 26 years experience who genuinely cares about practitioners.
NOT like a LinkedIn ghostwriter. NOT like an AI content generator.
Short paragraphs. Direct. Real. Warm but not soft.
"""


# ── Feature 1: Link → LinkedIn Post ───────────────────────
@app.route('/api/link-to-post', methods=['POST'])
def link_to_post():
    data = request.json
    url = data.get('url', '')
    context = data.get('context', '')
    provider = data.get('provider', 'openai')
    api_key = data.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API key required'}), 400

    # First fetch the URL content
    fetch_prompt = f"""
I need you to read this URL and extract the key insights: {url}

If you cannot access the URL, use this context instead: {context}

Extract:
1. Main point in one sentence
2. Why QA/engineering leaders should care
3. Most surprising or counterintuitive insight
4. Practical implication for QA teams

Return as JSON with keys: main_point, why_care, surprise, implication
Return ONLY the JSON, no markdown.
"""

    voice_context = build_voice_context()

    post_prompt = f"""
{voice_context}

TASK: Write 3 different LinkedIn post options for Tatyana sharing this content:
URL: {url}
Context: {context}

Write 3 posts, each using a different format:
Post 1: Lead with a provocative question or surprising stat
Post 2: Lead with her personal take/reaction  
Post 3: Lead with community angle — why her audience specifically needs this

Each post: 3-5 short paragraphs, ends with a question to drive comments.
Include 3-5 relevant hashtags at the end.
Include [LINK] where the URL should be inserted.

Return as JSON array with 3 objects, each having: format, hook, body, hashtags
Return ONLY the JSON array, no markdown.
"""

    try:
        result = call_llm(post_prompt, provider, api_key)
        clean = result.strip().replace('```json', '').replace('```', '').strip()
        posts = json.loads(clean)
        return jsonify({'posts': posts, 'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Feature 2: Event Content Machine ──────────────────────
@app.route('/api/event-content', methods=['POST'])
def event_content():
    data = request.json
    event_name = data.get('event_name', '')
    event_date = data.get('event_date', '')
    event_location = data.get('event_location', '')
    event_url = data.get('event_url', '')
    event_details = data.get('details', '')
    provider = data.get('provider', 'openai')
    api_key = data.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API key required'}), 400

    voice_context = build_voice_context()

    # Check if this is one of her known events
    known_events = {e['name']: e for e in KB['upcoming_events']}
    extra_context = ''
    for name, evt in known_events.items():
        if name.lower() in event_name.lower():
            extra_context = f"This is her own conference she organises. Hashtag: {evt['hashtag']}. {evt['description']}"
            break

    prompt = f"""
{voice_context}

TASK: Generate a complete content sequence for this event:
Event: {event_name}
Date: {event_date}
Location: {event_location}
URL: {event_url}
Details: {event_details}
{extra_context}

Generate 5 LinkedIn posts as a sequence:
1. ANNOUNCEMENT (2-3 weeks before): Build excitement, why this event is different
2. SPEAKER SPOTLIGHT (1 week before): Highlight what attendees will learn
3. DAY-OF ENERGY (day of event): Live energy post, FOMO for those not there
4. DURING EVENT (real-time update): Key insight or moment from the room
5. RECAP (day after): Honest reflection, lessons learned, gratitude

Each post: authentic Tatyana voice, 2-4 short paragraphs, engagement question.
Include timing label and relevant hashtags.

Return as JSON array of 5 objects with: timing, title, body, hashtags, tip
Return ONLY the JSON array, no markdown.
"""

    try:
        result = call_llm(prompt, provider, api_key)
        clean = result.strip().replace('```json', '').replace('```', '').strip()
        posts = json.loads(clean)
        return jsonify({'sequence': posts, 'event': event_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Feature 3: Podcast Repurposer ─────────────────────────
@app.route('/api/podcast-repurpose', methods=['POST'])
def podcast_repurpose():
    data = request.json
    episode_title = data.get('title', '')
    guest_name = data.get('guest', '')
    guest_title = data.get('guest_title', '')
    transcript_or_summary = data.get('content', '')
    episode_url = data.get('url', '')
    provider = data.get('provider', 'openai')
    api_key = data.get('api_key', '')

    if not api_key:
        return jsonify({'error': 'API key required'}), 400

    voice_context = build_voice_context()

    prompt = f"""
{voice_context}

TASK: Repurpose this podcast episode into 5 LinkedIn posts for Tatyana.

Podcast: {KB['podcast']['name']}
Episode: {episode_title}
Guest: {guest_name} — {guest_title}
Episode URL: {episode_url}
Content/Summary: {transcript_or_summary}

Generate 5 different LinkedIn posts from this episode:
1. EPISODE ANNOUNCEMENT: Launch post driving listeners to the episode
2. KEY QUOTE: Most powerful thing the guest said (or would say based on their background)
3. INSIGHT THREAD: The single most counterintuitive insight from the conversation
4. PRACTICAL TAKEAWAY: What QA teams can do TODAY based on this episode
5. COMMUNITY QUESTION: Open-ended question this episode raises for the community

Each post: Tatyana's authentic voice, 2-4 paragraphs, ends with engagement hook.
Include [EPISODE_LINK] where relevant.

Return as JSON array of 5 objects with: type, title, body, hashtags, best_time_to_post
Return ONLY the JSON array, no markdown.
"""

    try:
        result = call_llm(prompt, provider, api_key)
        clean = result.strip().replace('```json', '').replace('```', '').strip()
        posts = json.loads(clean)
        return jsonify({'posts': posts, 'episode': episode_title})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5400))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'
    print(f"\n  Tatyana's Content Agent")
    print(f"  Running on http://localhost:{port}\n")
    app.run(host='0.0.0.0', port=port, debug=debug)
