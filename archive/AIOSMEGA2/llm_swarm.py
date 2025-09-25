#!/usr/bin/env python3
import json
import hashlib
import argparse
import concurrent.futures
from pathlib import Path
from datetime import datetime

class LLMSwarm:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.cache_dir = self.aios_dir / "llm_cache"
        self.cache_dir.mkdir(exist_ok=True)

    def get_cache_key(self, question):
        return hashlib.md5(question.encode()).hexdigest()

    def check_cache(self, question):
        cache_key = self.get_cache_key(question)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
                # Check if cache is fresh (24 hours)
                cached_time = datetime.fromisoformat(data['timestamp'])
                if (datetime.now() - cached_time).total_seconds() < 86400:
                    return data
        return None

    def save_cache(self, question, responses):
        cache_key = self.get_cache_key(question)
        cache_file = self.cache_dir / f"{cache_key}.json"

        data = {
            'question': question,
            'timestamp': datetime.now().isoformat(),
            'responses': responses
        }

        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)

    def query_llm(self, model_name, question):
        import os
        # Check for API keys
        if model_name == 'gpt4' and not os.environ.get('OPENAI_API_KEY'):
            raise ValueError(f"❌ Error: OPENAI_API_KEY not set for {model_name}")
        elif model_name == 'claude' and not os.environ.get('ANTHROPIC_API_KEY'):
            raise ValueError(f"❌ Error: ANTHROPIC_API_KEY not set for {model_name}")
        elif model_name == 'gemini' and not os.environ.get('GOOGLE_API_KEY'):
            raise ValueError(f"❌ Error: GOOGLE_API_KEY not set for {model_name}")

        # If API keys exist, would make actual API calls here
        # For now, return placeholder with API key check
        return {
            'model': model_name,
            'response': f"{model_name}: Would query with API key (key exists)",
            'confidence': 0.85
        }

    def ask_swarm(self, question):
        # Check cache first
        cached = self.check_cache(question)
        if cached:
            print("📦 Using cached responses")
            return cached['responses']

        models = ['gpt4', 'claude', 'llama', 'gemini']
        responses = []

        print(f"\n🐝 Querying {len(models)} LLMs in parallel...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self.query_llm, model, question): model
                      for model in models}

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                responses.append(result)
                print(f"✓ {result['model']} responded")

        # Save to cache
        self.save_cache(question, responses)

        return responses

    def analyze_responses(self, responses):
        print("\n📊 Response Analysis:")

        # Find consensus
        common_words = {}
        for resp in responses:
            words = resp['response'].lower().split()
            for word in words:
                if len(word) > 5:  # Only longer words
                    common_words[word] = common_words.get(word, 0) + 1

        # Top consensus terms
        consensus = sorted(common_words.items(), key=lambda x: x[1], reverse=True)[:5]

        if consensus:
            print("\n🤝 Consensus themes:")
            for word, count in consensus:
                if count > 1:
                    print(f"  • '{word}' mentioned by {count} models")

        # Show all responses
        print("\n💬 All Responses:")
        for resp in responses:
            print(f"\n{resp['model']} (confidence: {resp['confidence']:.0%}):")
            print(f"  {resp['response']}")

    def clear_cache(self):
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
        print(f"🗑 Cleared {len(list(self.cache_dir.glob('*.json')))} cached responses")

def main():
    parser = argparse.ArgumentParser(description='LLM Swarm - Multi-model AI queries')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    ask_parser = subparsers.add_parser('ask', help='Query multiple LLMs')
    ask_parser.add_argument('question', help='Question to ask')

    cache_parser = subparsers.add_parser('cache', help='Cache management')
    cache_parser.add_argument('action', choices=['clear', 'list'])

    args = parser.parse_args()
    swarm = LLMSwarm()

    if args.command == 'ask':
        responses = swarm.ask_swarm(args.question)
        swarm.analyze_responses(responses)
    elif args.command == 'cache':
        if args.action == 'clear':
            swarm.clear_cache()
        elif args.action == 'list':
            cache_files = list(swarm.cache_dir.glob("*.json"))
            print(f"📦 Cached queries: {len(cache_files)}")
            for f in cache_files[:10]:
                with open(f) as fh:
                    data = json.load(fh)
                    print(f"  • {data['question'][:50]}...")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()