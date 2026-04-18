from json import loads
from operator import itemgetter
response = http_request(url='https://jsonplaceholder.typicode.com/todos').data.decode()
todos = loads(response)
pending_todos = sorted([todo for todo in todos if not todo['completed']], key=itemgetter('id'), reverse=True)
with open('/workspace/pending_todos.json', 'w') as f:
    pending_todos_json = {'todos': pending_todos}
    import json
    json.dump(pending_todos_json, f)
