import json

# Load JSON data from response
response_data = json.load(open('/workspace/http_responses/resp_20260418_061312_713473.json', 'r'))

# Filter out items where completed is false and sort by id in descending order
pending_todos = sorted([todo for todo in response_data if not todo['completed']], key=lambda x: x['id'], reverse=True)

# Save the result to a file named pending_todos.json
with open('/workspace/pending_todos.json', 'w') as f:
    json.dump(pending_todos, f, indent=2)

# Read back the file and confirm the number of pending todos
with open('/workspace/pending_todos.json', 'r') as f:
    print(f'Number of pending todos: {len(json.load(f))}')
