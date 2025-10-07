#!/usr/bin/env python3
"""
Knowledge Base Management Tool for HDFC CollectNow Chatbot
o
Usage:
    python manage_kb.py clear          # Delete all KB entries
    python manage_kb.py view           # View all KB entries
    python manage_kb.py count          # Count total entries
    python manage_kb.py seed           # Seed from knowledge_base.json
    python manage_kb.py seed --sample  # Seed from sample_kb.json
    python manage_kb.py export         # Export current KB to JSON file
    python manage_kb.py reset          # Clear and reseed from default
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app import create_app, db
from app.models import KnowledgeBaseEntry


KB_PATH = Path("kb/knowledge_base.json")
SAMPLE_KB_PATH = Path("kb/sample_kb.json")
EXPORT_PATH = Path("kb/kb_export_{timestamp}.json")


def clear_kb() -> int:
    """Delete all knowledge base entries."""
    app = create_app()
    with app.app_context():
        count = KnowledgeBaseEntry.query.count()
        if count == 0:
            print("✓ Knowledge base is already empty.")
            return 0
        
        # Confirm deletion
        print(f"⚠️  Warning: This will delete {count} knowledge base entries!")
        response = input("Type 'YES' to confirm deletion: ")
        
        if response.strip().upper() != 'YES':
            print("❌ Operation cancelled.")
            return 1
        
        # Delete all entries
        KnowledgeBaseEntry.query.delete()
        db.session.commit()
        
        print(f"✓ Successfully deleted {count} knowledge base entries.")
        return 0


def view_kb(limit: int | None = None, detailed: bool = False) -> int:
    """View knowledge base entries."""
    app = create_app()
    with app.app_context():
        query = KnowledgeBaseEntry.query.order_by(KnowledgeBaseEntry.id.asc())
        
        if limit:
            entries = query.limit(limit).all()
        else:
            entries = query.all()
        
        if not entries:
            print("ℹ️  Knowledge base is empty.")
            return 0
        
        total_count = KnowledgeBaseEntry.query.count()
        print(f"\n{'='*80}")
        print(f"Knowledge Base Entries ({len(entries)} of {total_count} shown)")
        print(f"{'='*80}\n")
        
        for idx, entry in enumerate(entries, start=1):
            print(f"[{entry.id}] Question: {entry.question}")
            
            if detailed:
                answer_preview = entry.answer[:200] + "..." if len(entry.answer) > 200 else entry.answer
                print(f"    Answer: {answer_preview}")
                
                tags = entry.tags_as_list()
                if tags:
                    print(f"    Tags: {', '.join(tags)}")
                
                print(f"    Created: {entry.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"    Updated: {entry.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            print()
        
        if limit and total_count > limit:
            print(f"... and {total_count - limit} more entries")
            print(f"Use --all flag to view all entries\n")
        
        return 0


def count_kb() -> int:
    """Count knowledge base entries."""
    app = create_app()
    with app.app_context():
        total = KnowledgeBaseEntry.query.count()
        
        print(f"\nKnowledge Base Statistics:")
        print(f"{'='*40}")
        print(f"Total entries: {total}")
        
        if total > 0:
            # Get tag statistics
            all_entries = KnowledgeBaseEntry.query.all()
            tag_counts: dict[str, int] = {}
            
            for entry in all_entries:
                tags = entry.tags_as_list()
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            if tag_counts:
                print(f"\nTag distribution:")
                for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
                    print(f"  - {tag}: {count}")
        
        print()
        return 0


def seed_kb(source_file: Path) -> int:
    """Seed knowledge base from JSON file."""
    if not source_file.exists():
        print(f"❌ Error: File not found: {source_file}")
        print(f"   Please create {source_file} or use --sample flag for sample data.")
        return 1
    
    try:
        data = json.loads(source_file.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {source_file}")
        print(f"   {e}")
        return 1
    
    if not isinstance(data, list):
        print(f"❌ Error: {source_file} must contain a JSON array of entries.")
        return 1
    
    app = create_app()
    with app.app_context():
        existing_count = KnowledgeBaseEntry.query.count()
        
        if existing_count > 0:
            print(f"⚠️  Warning: Knowledge base already has {existing_count} entries!")
            print("   New entries will be added or update existing ones.")
            response = input("Continue? (y/N): ")
            
            if response.strip().lower() != 'y':
                print("❌ Operation cancelled.")
                return 1
        
        added = 0
        updated = 0
        errors = 0
        
        for idx, entry_data in enumerate(data, start=1):
            try:
                question = entry_data.get("question", "").strip()
                answer = entry_data.get("answer", "").strip()
                tags = entry_data.get("tags", [])
                
                if not question or not answer:
                    print(f"⚠️  Skipping entry #{idx}: Missing question or answer")
                    errors += 1
                    continue
                
                tags_json = json.dumps(tags, ensure_ascii=False)
                
                existing = KnowledgeBaseEntry.query.filter_by(question=question).first()
                
                if existing:
                    existing.answer = answer
                    existing.tags = tags_json
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    db.session.add(
                        KnowledgeBaseEntry(
                            question=question,
                            answer=answer,
                            tags=tags_json
                        )
                    )
                    added += 1
                
            except Exception as e:
                print(f"⚠️  Error processing entry #{idx}: {e}")
                errors += 1
        
        db.session.commit()
        
        print(f"\n{'='*60}")
        print(f"Knowledge Base Seeding Complete")
        print(f"{'='*60}")
        print(f"✓ Added: {added} entries")
        print(f"✓ Updated: {updated} entries")
        if errors > 0:
            print(f"⚠️  Errors: {errors} entries")
        print(f"Total entries in KB: {KnowledgeBaseEntry.query.count()}")
        print()
        
        return 0


def export_kb(output_file: Path | None = None) -> int:
    """Export knowledge base to JSON file."""
    app = create_app()
    with app.app_context():
        entries = KnowledgeBaseEntry.query.order_by(KnowledgeBaseEntry.id.asc()).all()
        
        if not entries:
            print("ℹ️  Knowledge base is empty. Nothing to export.")
            return 0
        
        export_data = []
        for entry in entries:
            export_data.append({
                "question": entry.question,
                "answer": entry.answer,
                "tags": entry.tags_as_list()
            })
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(f"kb/kb_export_{timestamp}.json")
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Exported {len(entries)} entries to: {output_file}")
        return 0


def reset_kb(use_sample: bool = False) -> int:
    """Clear and reseed knowledge base."""
    source = SAMPLE_KB_PATH if use_sample else KB_PATH
    
    if not source.exists():
        print(f"❌ Error: Source file not found: {source}")
        return 1
    
    app = create_app()
    with app.app_context():
        count = KnowledgeBaseEntry.query.count()
        
        if count > 0:
            print(f"⚠️  Warning: This will delete {count} existing entries and reseed!")
            response = input("Type 'YES' to confirm reset: ")
            
            if response.strip().upper() != 'YES':
                print("❌ Operation cancelled.")
                return 1
            
            # Clear existing
            KnowledgeBaseEntry.query.delete()
            db.session.commit()
            print(f"✓ Cleared {count} existing entries.")
        
        # Seed
        print(f"📝 Seeding from {source}...")
        return seed_kb(source)


def search_kb(query: str) -> int:
    """Search knowledge base by question or tags."""
    app = create_app()
    with app.app_context():
        # Search in questions
        results = KnowledgeBaseEntry.query.filter(
            KnowledgeBaseEntry.question.ilike(f"%{query}%")
        ).all()
        
        # Also search in tags
        tag_results = [
            entry for entry in KnowledgeBaseEntry.query.all()
            if query.lower() in [tag.lower() for tag in entry.tags_as_list()]
        ]
        
        # Combine and deduplicate
        all_results = list(set(results + tag_results))
        
        if not all_results:
            print(f"ℹ️  No results found for: {query}")
            return 0
        
        print(f"\n{'='*80}")
        print(f"Search Results for: '{query}' ({len(all_results)} found)")
        print(f"{'='*80}\n")
        
        for entry in all_results:
            print(f"[{entry.id}] {entry.question}")
            
            answer_preview = entry.answer[:150] + "..." if len(entry.answer) > 150 else entry.answer
            print(f"    {answer_preview}")
            
            tags = entry.tags_as_list()
            if tags:
                print(f"    Tags: {', '.join(tags)}")
            
            print()
        
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Knowledge Base Management Tool for HDFC CollectNow Chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_kb.py clear                    # Delete all entries
  python manage_kb.py view                     # View first 10 entries
  python manage_kb.py view --all              # View all entries
  python manage_kb.py view --detailed         # View with full details
  python manage_kb.py count                    # Show statistics
  python manage_kb.py seed                     # Seed from knowledge_base.json
  python manage_kb.py seed --sample           # Seed from sample_kb.json
  python manage_kb.py export                   # Export to timestamped file
  python manage_kb.py export --output my.json # Export to specific file
  python manage_kb.py reset                    # Clear and reseed
  python manage_kb.py search "payment"        # Search for entries
        """
    )
    
    parser.add_argument(
        'command',
        choices=['clear', 'view', 'count', 'seed', 'export', 'reset', 'search'],
        help='Command to execute'
    )
    
    parser.add_argument(
        '--sample',
        action='store_true',
        help='Use sample_kb.json instead of knowledge_base.json'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='View all entries (for view command)'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed information (for view command)'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (for export command)'
    )
    
    parser.add_argument(
        'search_query',
        nargs='?',
        help='Search query (for search command)'
    )
    
    args = parser.parse_args()
    
    try:
        if args.command == 'clear':
            return clear_kb()
        
        elif args.command == 'view':
            limit = None if args.all else 10
            return view_kb(limit=limit, detailed=args.detailed)
        
        elif args.command == 'count':
            return count_kb()
        
        elif args.command == 'seed':
            source = SAMPLE_KB_PATH if args.sample else KB_PATH
            return seed_kb(source)
        
        elif args.command == 'export':
            return export_kb(args.output)
        
        elif args.command == 'reset':
            return reset_kb(use_sample=args.sample)
        
        elif args.command == 'search':
            if not args.search_query:
                print("❌ Error: Search query required")
                print("   Usage: python manage_kb.py search \"your query\"")
                return 1
            return search_kb(args.search_query)
        
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())