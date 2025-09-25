#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from datetime import datetime

class IdeaRanker:
    def __init__(self):
        self.aios_dir = Path.home() / ".aios"
        self.aios_dir.mkdir(exist_ok=True)
        self.ideas_file = self.aios_dir / "ideas.txt"
        self.ranked_file = self.aios_dir / "ranked_ideas.txt"

    def load_ideas(self):
        if not self.ideas_file.exists():
            return []
        with open(self.ideas_file) as f:
            return [line.strip() for line in f if line.strip()]

    def save_ideas(self, ideas):
        with open(self.ideas_file, 'w') as f:
            f.write('\n'.join(ideas))

    def score_idea(self, idea):
        # Simple scoring heuristic (replace with LLM call)
        score = 0
        feasibility = 5
        impact = 5

        # Keywords for feasibility
        easy_words = ['simple', 'basic', 'quick', 'easy', 'small']
        hard_words = ['complex', 'difficult', 'advanced', 'large']

        idea_lower = idea.lower()
        for word in easy_words:
            if word in idea_lower:
                feasibility += 2

        for word in hard_words:
            if word in idea_lower:
                feasibility -= 2

        # Keywords for impact
        high_impact = ['critical', 'important', 'essential', 'key', 'major']
        low_impact = ['minor', 'nice-to-have', 'optional', 'small']

        for word in high_impact:
            if word in idea_lower:
                impact += 2

        for word in low_impact:
            if word in idea_lower:
                impact -= 2

        # Clamp values
        feasibility = max(1, min(10, feasibility))
        impact = max(1, min(10, impact))

        # Combined score (prioritize high impact, high feasibility)
        score = (impact * 2 + feasibility) / 3

        return {'idea': idea, 'score': score, 'impact': impact, 'feasibility': feasibility}

    def rank_ideas(self):
        ideas = self.load_ideas()
        if not ideas:
            print("No ideas to rank")
            return

        scored_ideas = [self.score_idea(idea) for idea in ideas]
        scored_ideas.sort(key=lambda x: x['score'], reverse=True)

        # Save ranked ideas
        with open(self.ranked_file, 'w') as f:
            f.write(f"# Ranked Ideas - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            for i, item in enumerate(scored_ideas, 1):
                f.write(f"{i}. [{item['score']:.1f}] (I:{item['impact']}/F:{item['feasibility']}) {item['idea']}\n")

        # Display results
        print("\n🏆 Top Ideas:")
        for i, item in enumerate(scored_ideas[:5], 1):
            print(f"{i}. Score: {item['score']:.1f} | Impact: {item['impact']}/10 | "
                  f"Feasibility: {item['feasibility']}/10")
            print(f"   {item['idea']}\n")

        print(f"✅ Full ranking saved to {self.ranked_file}")

    def add_idea(self, idea_text):
        ideas = self.load_ideas()
        ideas.append(idea_text)
        self.save_ideas(ideas)
        print(f"💡 Added: {idea_text}")
        print(f"Total ideas: {len(ideas)}")

    def pick_easy(self):
        ideas = self.load_ideas()
        scored = [self.score_idea(idea) for idea in ideas]

        # Filter for easy wins (high feasibility, decent impact)
        easy_wins = [s for s in scored if s['feasibility'] >= 7 and s['impact'] >= 5]
        easy_wins.sort(key=lambda x: x['score'], reverse=True)

        if easy_wins:
            print("\n🎯 Easy Wins:")
            for item in easy_wins[:3]:
                print(f"• {item['idea']}")
                print(f"  Score: {item['score']:.1f} | Impact: {item['impact']} | Feasibility: {item['feasibility']}\n")
        else:
            print("No easy wins found (high feasibility + decent impact)")

    def show_categories(self):
        ideas = self.load_ideas()
        scored = [self.score_idea(idea) for idea in ideas]

        high_impact = [s for s in scored if s['impact'] >= 8]
        easy_impl = [s for s in scored if s['feasibility'] >= 8]
        balanced = [s for s in scored if abs(s['impact'] - s['feasibility']) <= 2]

        print("\n📊 Ideas by Category:\n")
        print(f"High Impact ({len(high_impact)} ideas)")
        print(f"Easy Implementation ({len(easy_impl)} ideas)")
        print(f"Balanced ({len(balanced)} ideas)")

def main():
    parser = argparse.ArgumentParser(description='Idea Ranker')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    subparsers.add_parser('rank', help='Rank all ideas')

    add_parser = subparsers.add_parser('add', help='Add an idea')
    add_parser.add_argument('idea', help='Idea description')

    pick_parser = subparsers.add_parser('pick', help='Pick ideas by criteria')
    pick_parser.add_argument('--easy', action='store_true', help='Show easy wins')

    subparsers.add_parser('categories', help='Show ideas by category')

    args = parser.parse_args()
    ranker = IdeaRanker()

    if args.command == 'rank':
        ranker.rank_ideas()
    elif args.command == 'add':
        ranker.add_idea(args.idea)
    elif args.command == 'pick':
        if args.easy:
            ranker.pick_easy()
    elif args.command == 'categories':
        ranker.show_categories()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()