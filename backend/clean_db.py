import sqlite3

def clean_db():
    conn = sqlite3.connect('youtube_bot.db')
    c = conn.cursor()
    
    # Check how many are affected
    c.execute("SELECT video_id, title FROM videos WHERE key_points LIKE '%parse failed%'")
    rows = c.fetchall()
    print(f"Found {len(rows)} cached errors:")
    for r in rows:
        print(r)
        
    # Delete them to force re-fetch
    c.execute("DELETE FROM videos WHERE key_points LIKE '%parse failed%'")
    conn.commit()
    print("Deleted cached errors.")
    conn.close()

if __name__ == '__main__':
    clean_db()
