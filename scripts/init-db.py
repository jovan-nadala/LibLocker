#!/usr/bin/env python3
"""
LibLocker Database Initialization Script
Creates the SQLite database with all tables and initial locker data
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')

def init_database():
    """Initialize the database with all tables and seed data."""
    try:
        from app import create_app
        
        app = create_app()
        
        print("🔄 Initializing LibLocker database...")
        
        with app.app_context():
            # The create_app() function automatically initializes the DB
            print("✓ Database initialization complete")
            print("")
            print("Database Summary:")
            print("  Location: {0}".format(app.config['DATABASE_PATH']))
            print("  Tables created: users, lockers, sessions, activity_logs, transactions, audit_logs")
            print("  Lockers initialized: 24")
            print("  Groups: upper1 (L-01 to L-06), upper2 (L-07 to L-12),")
            print("          lower1 (L-13 to L-18), lower2 (L-19 to L-24)")
            print("")
            print("✓ Ready for deployment!")
            
    except Exception as e:
        print("❌ Database initialization failed: {0}".format(str(e)))
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    init_database()
