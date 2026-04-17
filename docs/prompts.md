Here are some complex, multi-step tasks you can ask the agent to perform in the terminal. They are designed to test the integration of multiple tools and the agent's ability to plan and execute.

---

## 🧪 Complex Test Prompts for the Sandbox Agent

### 1. **Multi‑Step Data Pipeline**

> Fetch a JSON dataset of todos from `https://jsonplaceholder.typicode.com/todos`, extract only the items where `completed` is `false`, sort them by `id` in descending order, and save the result as `pending_todos.json` in the workspace. Then read back the file and confirm how many pending todos there are.

**Tools exercised:** `http_request`, `execute_python`, `write_file`, `read_file`.

---

### 2. **Web Scraping with Playwright + Data Processing**

> Use Playwright to navigate to `https://books.toscrape.com`, extract the titles and prices of all books on the first page, save them as a CSV file named `books.csv` in the workspace. Then read the CSV file and print the average price of the books.

**Tools exercised:** `run_playwright_script`, `execute_python`, `write_file`, `read_file`.

---

### 3. **Dynamic Python Environment Setup**

> Install the `numpy` and `matplotlib` packages. Then write a Python script that generates a simple line plot of `y = x^2` for `x` from -10 to 10. Save the plot as `plot.png` in the workspace. Since we can't display it, just verify the file exists and report its size.

**Tools exercised:** `install_python_package`, `execute_python`, `run_shell_command`, `list_files`.

---

### 4. **Parallel Shell Commands and Error Recovery**

> Create a directory called `test_dir`. Inside it, create three text files: `a.txt`, `b.txt`, `c.txt` with the content "Hello A", "Hello B", and "Hello C" respectively. Then, using a single shell pipeline, concatenate all three files and count the total number of lines. Finally, clean up by deleting `test_dir` and everything inside it.

**Tools exercised:** `run_shell_command`, `write_file`, `execute_python` (or shell commands only).

---

### 5. **Large HTTP Response Exploration**

> Make a GET request to `https://jsonplaceholder.typicode.com/comments` (this returns 500 comments). Do **not** read the entire response into context. Instead, use `grep_file` to find all comments that contain the word "alias" and count how many there are. Then use `read_file_range` to show the first three matching comments.

**Tools exercised:** `http_request` (with file offloading), `grep_file`, `read_file_range`.

---

### 6. **Synthesise a Report from Multiple APIs**

> Fetch a random cat fact from `https://catfact.ninja/fact` and a random dog image URL from `https://dog.ceo/api/breeds/image/random`. Combine them into a single JSON object like `{"cat_fact": "...", "dog_image": "..."}` and save it as `pet_report.json`. Then read the file and print a fun sentence using both pieces of information.

**Tools exercised:** `http_request` (twice), `execute_python`, `write_file`, `read_file`.

---

### 7. **Simulate a Long‑Running Process**

> Write a Python script that prints numbers from 1 to 10 with a one-second delay between each. Execute it and show that it runs to completion. (The agent should note that it must wait for the script to finish, not just return immediately.)

**Tools exercised:** `execute_python` (with `time.sleep`).

---

### 8. **Playwright Form Interaction**

> Use Playwright to go to `https://httpbin.org/forms/post`, fill the form with a custom name and email (e.g., "Sandbox Agent" and "agent@test.com"), submit it, and print the JSON response returned by the server (which echoes the submitted data). Extract the submitted name from the response and confirm it matches.

**Tools exercised:** `run_playwright_script`, `execute_python` (to parse the response).

---

### 9. **Log Analysis Simulation**

> Generate a mock log file with 100 lines of random entries using a Python script. Then use shell commands (`grep`, `wc`, `awk`) to find how many lines contain "ERROR", and display the last 5 error lines.

**Tools exercised:** `execute_python`, `run_shell_command`.

---

### 10. **Full Workflow: Package Install → Web Scrape → CSV Export → Analysis**

> Install the Python package `pandas`. Then use Playwright to scrape the first 20 items from `https://quotes.toscrape.com/` (quote text and author). Save them as `quotes.csv` using pandas. Finally, load the CSV with pandas and print the author with the most quotes.

**Tools exercised:** `install_python_package`, `run_playwright_script`, `execute_python`, `read_file`.

---

## How to Use These Prompts

1. Start the agent: `python harness.py`
2. Copy and paste one of the prompts at the `You:` prompt.
3. Observe the agent's ReAct loop and tool usage.

These tasks are intentionally non‑trivial and will require the agent to chain multiple tools together. They are excellent for stress‑testing your sandbox setup.