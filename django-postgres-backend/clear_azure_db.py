#!/usr/bin/env python
"""
Script to clear all data from Azure database.

WARNING: This will delete ALL data from all tables!
Use with caution. Make sure you have backups if needed.

Usage:
    python clear_azure_db.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmacy_backend.settings')
django.setup()

from django.db import connection
from django.core.management import call_command
from django.apps import apps

def clear_all_data():
    """Delete all data from all tables while preserving table structure."""
    print("⚠️  WARNING: This will delete ALL data from the database!")
    confirm = input("Type 'DELETE ALL DATA' to confirm: ")
    
    if confirm != "DELETE ALL DATA":
        print("❌ Cancelled. No data was deleted.")
        return
    
    print("\n🔄 Starting database flush...")
    
    # Method 1: Use Django's flush command (recommended)
    call_command('flush', '--noinput', verbosity=2)
    
    print("\n✅ Database flushed successfully!")
    print("📋 All data has been deleted, but table structure is preserved.")
    print("\n💡 Next steps:")
    print("   1. Run migrations if needed: python manage.py migrate")
    print("   2. Create superuser if needed: python manage.py createsuperuser")
    print("   3. Load initial data if you have fixtures")

def clear_all_data_direct_sql():
    """Alternative: Use direct SQL to truncate all tables."""
    print("⚠️  WARNING: This will delete ALL data from the database!")
    confirm = input("Type 'DELETE ALL DATA' to confirm: ")
    
    if confirm != "DELETE ALL DATA":
        print("❌ Cancelled. No data was deleted.")
        return
    
    print("\n🔄 Truncating all tables...")
    
    with connection.cursor() as cursor:
        # Disable foreign key checks temporarily
        cursor.execute("SET session_replication_role = 'replica';")
        
        # Get all table names
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            AND tablename NOT LIKE 'django_%'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        # Also get Django tables
        cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            AND tablename LIKE 'django_%'
        """)
        django_tables = [row[0] for row in cursor.fetchall()]
        
        all_tables = tables + django_tables
        
        # Truncate each table
        for table in all_tables:
            try:
                cursor.execute(f'TRUNCATE TABLE "{table}" CASCADE;')
                print(f"   ✓ Truncated: {table}")
            except Exception as e:
                print(f"   ✗ Error truncating {table}: {e}")
        
        # Re-enable foreign key checks
        cursor.execute("SET session_replication_role = 'origin';")
    
    print("\n✅ All tables truncated successfully!")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--sql":
        clear_all_data_direct_sql()
    else:
        clear_all_data()

