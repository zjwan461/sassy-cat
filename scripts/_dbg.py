import sqlite3
p=r'C:\Users\1\AppData\Roaming\sassy-cat\messages.sqlite'
con=sqlite3.connect(p); con.row_factory=sqlite3.Row
for c in con.execute("select id,title,created_at,updated_at from conversations order by updated_at desc limit 5"):
    print('conv', dict(c))
    rows=list(con.execute("select id,role,created_at,substr(content,1,30) c from messages where session_id=? order by created_at asc",(c['id'],)))
    print('  count',len(rows))
    for r in rows[:5]: print('   ',dict(r))
    # duplicates timestamps
    ts=[r['created_at'] for r in rows]
    print('  dup timestamps', len(ts)-len(set(ts)))
con.close()
