import json
from operator import itemgetter
todos = json.load(open('/workspace/response_123.txt'))
pending_todos = sorted([todo for todo in todos if not todo['completed']], key=itemgetter('id'), reverse=True)
with open('/workspace/pending_todos.json', 'w') as f:
    json.dump(pending_todos, f, indent=4)
done_count = len(pending_todos)
done_count
