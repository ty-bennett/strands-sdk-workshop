# Creating and Hosting Your Own Agents on AWS

### Background
- I found out was Strands SDK was at an OSS AI conference in Durham, NC courstesy of Darko Meszaros. Did some tinkering afterwards and came up with the idea
of this as a workshop that students could participate in. Using AWS services is also right up my alley because of my involvement with the AWS CC and my Amazon certification, and other cloud experience.

## 1. Setup

### Prerequisites

Before starting the workshop, you'll need:
1. Python 3.12 or higher installed on your system
2. AWS Bedrock access credentials to interact with the Claude Sonnet 4.5 model
3. A CSV file of your assignments for the later part of the workshop

### 1.1 Verify Python Version

First, check that you have Python 3.12 or higher installed:

**On Unix/Linux/macOS:**
```bash
python3 --version
```

**On Windows:**
```bash
python --version
```

You should see output like `Python 3.12.x` or higher. If your version is below 3.12, please install or upgrade Python before continuing.

### 1.2 Create Virtual Environment

Create an isolated Python environment for the workshop:

**On Unix/Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows (Command Prompt):**
```bash
python -m venv venv
venv\Scripts\activate.bat
```

**On Windows (PowerShell):**
```bash
python -m venv venv
venv\Scripts\Activate.ps1
```

Once activated, your terminal prompt should show `(venv)` at the beginning, indicating you're working in the virtual environment.

### 1.3 Install Dependencies

With your virtual environment activated, install the required packages:

```bash
pip install -r requirements.txt
```

This will install:
- `strands-agents`: The Strands SDK for building agents
- `strands-agents-tools`: Pre-built tools including web search
- Other required dependencies

### 1.4 Configure AWS Credentials

To use AWS Bedrock, you need to set up your AWS credentials as environment variables.

**On Unix/Linux/macOS:**
```bash
export AWS_ACCESS_KEY_ID="your-access-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-access-key"
export AWS_DEFAULT_REGION="us-east-1"
```

**On Windows (Command Prompt):**
```bash
set AWS_ACCESS_KEY_ID=your-access-key-id
set AWS_SECRET_ACCESS_KEY=your-secret-access-key
set AWS_DEFAULT_REGION=us-east-1
```

**On Windows (PowerShell):**
```bash
$env:AWS_ACCESS_KEY_ID="your-access-key-id"
$env:AWS_SECRET_ACCESS_KEY="your-secret-access-key"
$env:AWS_DEFAULT_REGION="us-east-1"
```

**Note:** Replace `your-access-key-id` and `your-secret-access-key` with your actual AWS credentials. If you don't have AWS Bedrock access yet, contact your instructor or AWS administrator.

**Important:** These environment variables are only set for your current terminal session. If you close the terminal, you'll need to set them again. For persistent configuration, consider adding them to your shell profile (`~/.bashrc`, `~/.zshrc`, etc. on Unix/macOS) or using Windows environment variable settings.

## 2. Stage One: Building Your First Agent

In Stage One, you'll create a basic Academic Advisor Agent that uses pre-built tools from the Strands SDK. This introduces you to agent fundamentals: models, system prompts, and tool integration.

### Learning Objectives

By the end of Stage One, you will:
- Understand how to create an agent using the Strands SDK
- Configure AWS Bedrock as your language model
- Load and use system prompts to define agent behavior
- Integrate pre-built tools like web_search
- Invoke your agent and interpret its responses

### 2.1 Create the Agent File

Create a new file called `agent.py` in your project directory:

```bash
touch agent.py
```

Open `agent.py` in your text editor and let's build the agent step by step.

### 2.2 Import Required Libraries

Start by importing the necessary modules:

```python
import os
from strands import Agent
from strands.models import BedrockModel
from strands_tools import web_search
```

**What's happening here:**
- `Agent`: The main class for creating agents in Strands SDK
- `BedrockModel`: Connects your agent to AWS Bedrock (Claude Sonnet 4.5)
- `web_search`: A pre-built tool that lets your agent search the web for information

### 2.3 Validate AWS Credentials

Before connecting to AWS Bedrock, verify that your credentials are configured:

```python
def validate_aws_credentials():
    """
    Validate that required AWS credentials are configured.
    
    Raises:
        ValueError: If any required AWS environment variables are missing
    """
    required_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError("AWS credentials not configured. Please set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION")

# Run validation
validate_aws_credentials()
```

**What's happening here:**
- This function checks that all three required AWS environment variables are set
- If any are missing, it raises a clear error message telling you what to fix
- This prevents cryptic errors later when trying to connect to Bedrock

### 2.4 Load the System Prompt

The system prompt defines your agent's personality and behavior. Create a function to load it from a file:

```python
def load_system_prompt(filepath: str = "system_prompt.txt") -> str:
    """
    Load system prompt from file.
    
    Args:
        filepath: Path to system prompt file (default: "system_prompt.txt")
    
    Returns:
        System prompt content as string
    
    Raises:
        FileNotFoundError: If system prompt file is not found
    """
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"System prompt file not found: {filepath}. This file is required for agent operation.")
```

**What's happening here:**
- This function reads the system prompt from a text file
- Using a file makes it easy to modify the agent's personality without changing code
- If the file is missing, you get a clear error message

### 2.5 Create the System Prompt File

Create a file called `system_prompt.txt` in the same directory as `agent.py`:

```bash
touch system_prompt.txt
```

Add the following content to `system_prompt.txt`:

```
You are a sharp academic advisor giving a student their morning briefing.

Structure your response exactly like this:

SITUATION — one blunt sentence on how heavy this week is

TODAY — bullets for what must happen today, in priority order

THIS WEEK — a day-by-day time block plan (Mon through Sun).
  For each day list the tasks and how long to spend on each,
  using the estimated_hours from the CSV to guide the schedule.
  Example: "Tuesday: 2h CSCE 350 HW3, 1h ENGL essay draft"

HEADS UP — anything due next week worth starting now

TIP — one concrete study tip based on what's coming up.
  Use web_search if a subject-specific tip would genuinely help.

Keep it tight. Direct. No filler.
```

**What's happening here:**
- This prompt defines the agent's personality (sharp, direct academic advisor)
- It specifies the exact output structure with five sections
- It tells the agent when to use the web_search tool (for subject-specific tips)

### 2.6 Configure the Bedrock Model

Now configure the AWS Bedrock model that will power your agent:

```python
# Create the model instance
model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5")
```

**What's happening here:**
- `BedrockModel` creates a connection to AWS Bedrock
- `model_id` specifies which model to use (Claude Sonnet 4.5 in this case)
- This model will handle all natural language understanding and generation

### 2.7 Create the Agent

Now bring it all together to create your agent:

```python
# Create the agent
agent = Agent(
    model=model,
    system_prompt=load_system_prompt(),
    tools=[web_search],
)
```

**What's happening here:**
- `Agent()` creates your agent instance
- `model`: The Bedrock model you configured
- `system_prompt`: The personality and instructions loaded from the file
- `tools`: A list of tools the agent can use (just web_search for now)

### 2.8 Test Your Agent

Add a simple test at the bottom of your file:

```python
if __name__ == "__main__":
    agent("What are some effective study techniques for computer science students?")
```

**What's happening here:**
- This code only runs when you execute the file directly (not when importing it)
- It invokes the agent with a simple question
- The agent will use the system prompt to structure its response
- It may use web_search to find current study tips

### 2.9 Run Your Agent

Save your `agent.py` file and run it:

```bash
python agent.py
```

**Expected Output:**

You should see output structured according to your system prompt:

```
SITUATION — Light week, good time to get ahead on projects

TODAY — 
• Review CS fundamentals (data structures, algorithms)
• Set up study schedule for the week

THIS WEEK —
Monday: 2h practice coding problems
Tuesday: 1.5h review lecture notes, 1h work on assignments
Wednesday: 2h deep work on project
Thursday: 1h review session with study group
Friday: 1.5h finish weekly assignments
Saturday: (catch-up buffer)
Sunday: (rest and plan next week)

HEADS UP — Start thinking about midterm preparation if exams are coming up

TIP — Use spaced repetition for memorizing algorithms. Tools like Anki work well for CS concepts. Practice coding by hand to prepare for technical interviews.
```

**Note:** The actual output will vary based on what the model generates and whether it uses web_search.

### 2.10 Understanding What Just Happened

Let's break down the agent's behavior:

1. **You invoked the agent** with a natural language question
2. **The agent read its system prompt** to understand its role and output format
3. **The agent considered its tools** (web_search) and decided whether to use them
4. **The agent generated a response** following the five-section structure
5. **You received structured output** that matches the system prompt's format

This is the core agent workflow: **Input → Tool Use (optional) → LLM Generation → Output**

### 2.11 Experiment with Your Agent

Try asking different questions:

```python
if __name__ == "__main__":
    # Try these different prompts:
    agent("Give me study tips for preparing for a math exam")
    # agent("How should I manage my time with multiple projects due?")
    # agent("What are effective note-taking strategies?")
```

Notice how the agent:
- Always follows the five-section structure (because of the system prompt)
- May use web_search for subject-specific advice
- Adapts its content to your question

### 2.12 Stage One Complete!

Congratulations! You've built your first AI agent. You now understand:
- How to configure AWS Bedrock as your model
- How to define agent behavior with system prompts
- How to integrate pre-built tools
- How to invoke and test your agent

**Next Step:** In Stage Two, you'll create a custom tool that reads assignment data from CSV files and generates personalized daily briefings. This will transform your agent from a general study advisor into a personalized academic assistant.

---

## 3. Stage Two: Creating a Custom Assignment Tracker Tool

In Stage One, you used pre-built tools from the Strands SDK. Now you'll learn to create your own custom tool that reads CSV files, categorizes assignments by deadline, calculates priorities, and formats structured output for your agent.

### Learning Objectives

By the end of Stage Two, you will:
- Understand how to create custom tools using the `@tool` decorator
- Parse and validate CSV data with proper error handling
- Implement date-based categorization logic
- Calculate priority scores to rank assignments
- Format structured output for agent consumption
- Test your tool with various CSV inputs

### 3.1 Understanding the Assignment Tracker Tool

The Assignment Tracker Tool will:
1. **Read** a CSV file containing assignment data
2. **Filter** out completed assignments
3. **Categorize** assignments into four buckets based on due dates:
   - **Overdue**: Due before today
   - **Due Today**: Due today
   - **Due This Week**: Due after today but before the week ends (Sunday)
   - **Upcoming**: Due after this week
4. **Prioritize** assignments within each bucket using a priority score
5. **Format** the output as structured text for the agent

### 3.2 Create Your Assignment CSV File

Before building the tool, create a CSV file with your assignments. Create a file called `assignments.csv`:

```bash
touch assignments.csv
```

Add the following content (or use your own assignments):

```csv
course,assignment,due_date,type,estimated_hours,status,notes
CSCE 350,HW5 - Dynamic Programming,2026-04-09,homework,3,not started,Focus on memoization techniques
ENGL 101,Persuasive Essay Draft,2026-04-10,essay,2.5,in progress,Need to add counterarguments
MATH 251,Quiz 4 Preparation,2026-04-08,exam,1.5,not started,Covers sections 6.1-6.3
CSCE 350,Lab 7 - Binary Search Trees,2026-04-11,lab,2,not started,Implement insert and delete operations
HIST 201,Chapter 8 Reading Notes,2026-04-09,reading,1,in progress,Half done
PHYS 207,Problem Set 6,2026-04-12,homework,4,not started,Thermodynamics problems
ENGL 101,Peer Review Comments,2026-04-08,homework,0.5,not started,Review 2 classmates' essays
MATH 251,Exam 3 Study Guide,2026-04-11,exam,3.5,in progress,Create formula sheet
CSCE 350,Project Milestone 2,2026-04-12,project,5,in progress,Complete algorithm implementation
HIST 201,Discussion Post Response,2026-04-10,homework,1,not started,Respond to at least 3 peers
```

**CSV Format Requirements:**
- **course**: Course code or name (e.g., "CSCE 350", "ENGL 101")
- **assignment**: Assignment name or description
- **due_date**: Date in YYYY-MM-DD format (e.g., "2026-04-09")
- **type**: Assignment type (homework, exam, project, essay, lab, reading)
- **estimated_hours**: Estimated completion time in hours (e.g., "3", "2.5")
- **status**: Current status (not started, in progress, complete)
- **notes**: Optional notes or reminders (can be empty)

### 3.3 Import Additional Libraries

At the top of your `agent.py` file, add these imports (if not already present):

```python
import csv
from datetime import date, datetime
```

**What's happening here:**
- `csv`: Python's built-in CSV parsing library
- `date`, `datetime`: For working with dates and comparing deadlines

### 3.4 Create the Priority Score Calculator

Before building the main tool, create a helper function to calculate priority scores:

```python
def calculate_priority_score(days_remaining: int, estimated_hours: float, 
                            days_until_due_weight: float = 2.0, 
                            effort_weight: float = 1.0) -> float:
    """
    Calculate priority score for an assignment.
    Lower score = higher priority (more urgent).
    
    Args:
        days_remaining: Number of days until due date
        estimated_hours: Estimated hours to complete assignment
        days_until_due_weight: Weight for days remaining (default 2.0)
        effort_weight: Weight for estimated hours (default 1.0)
    
    Returns:
        Priority score (lower is higher priority)
    """
    return (days_until_due_weight * days_remaining) + (effort_weight * estimated_hours)
```

**What's happening here:**
- **Priority Score Formula**: `(2.0 × days_remaining) + (1.0 × estimated_hours)`
- **Lower score = higher priority**: Assignments due sooner get lower scores
- **Urgency weighted more than effort**: The default weight of 2.0 for days emphasizes deadline urgency
- **Example**: An assignment due in 1 day with 3 hours of work gets score = (2.0 × 1) + (1.0 × 3) = 5.0
- **Example**: An assignment due in 3 days with 1 hour of work gets score = (2.0 × 3) + (1.0 × 1) = 7.0 (lower priority)

### 3.5 Create the Assignment Tracker Tool with @tool Decorator

Now create the main tool function. Add this before your agent creation:

```python
@tool
def load_assignments(filepath: str, days_until_due_weight: float = 2.0, 
                    effort_weight: float = 1.0) -> str:
    """
    Reads assignment CSV, categorizes by deadline, and returns formatted text.
    
    Args:
        filepath: Path to CSV file with columns: course, assignment, due_date,
                  type, estimated_hours, status, notes
        days_until_due_weight: Weight for urgency in priority calculation (default 2.0)
        effort_weight: Weight for effort in priority calculation (default 1.0)
    
    Returns:
        Formatted string with categorized assignments and metadata
    
    Raises:
        FileNotFoundError: If filepath does not exist
        ValueError: If CSV is malformed or missing required columns
        ValueError: If due_date format is invalid
    """
```

**What's happening here:**
- **@tool decorator**: This tells Strands SDK that this function is a tool the agent can use
- **Type hints**: Specify parameter types (str, float) and return type (str)
- **Docstring**: Describes what the tool does, its parameters, and what it returns
- **The agent will see this docstring** and use it to understand when and how to call the tool

### 3.6 Step 1: Handle File Not Found Errors

Inside the `load_assignments` function, start with file handling:

```python
    # Handle FileNotFoundError with descriptive message
    try:
        f = open(filepath, newline="")
    except FileNotFoundError:
        return f"Assignment file not found: {filepath}"
```

**What's happening here:**
- Try to open the file specified by `filepath`
- If the file doesn't exist, return a clear error message
- The `newline=""` parameter is recommended for CSV files to handle line endings correctly

### 3.7 Step 2: Initialize Date Variables and Buckets

Add this inside the try block:

```python
    try:
        today = date.today()
        week_end = date.fromordinal(today.toordinal() + (6 - today.weekday()))

        buckets = {
            "overdue": [],
            "due_today": [],
            "due_this_week": [],
            "upcoming": []
        }
```

**What's happening here:**
- **today**: Get the current date
- **week_end**: Calculate the end of the current week (Sunday)
  - `today.weekday()` returns 0 for Monday, 6 for Sunday
  - `6 - today.weekday()` gives days until Sunday
  - `date.fromordinal()` converts the ordinal back to a date
- **buckets**: Create a dictionary to store assignments in four categories

### 3.8 Step 3: Validate CSV Columns

Add CSV validation logic:

```python
        # CSV column validation with missing column reporting
        reader = csv.DictReader(f)
        required_columns = {"course", "assignment", "due_date", "type", "estimated_hours", "status", "notes"}
        
        # Check if fieldnames exist (handles empty or malformed CSV)
        if reader.fieldnames is None:
            return "Malformed CSV file: unable to read header row"
        
        actual_columns = set(reader.fieldnames)
        missing_columns = required_columns - actual_columns
        
        if missing_columns:
            return f"Missing required columns: {', '.join(sorted(missing_columns))}"
```

**What's happening here:**
- **csv.DictReader**: Reads CSV and converts each row to a dictionary using header names as keys
- **required_columns**: Define the seven required columns as a set
- **Check fieldnames**: Ensure the CSV has a valid header row
- **Set difference**: `required_columns - actual_columns` finds missing columns
- **Error message**: If columns are missing, return a descriptive error listing them

### 3.9 Step 4: Parse and Categorize Assignments

Add the main parsing loop:

```python
        # Date parsing error handling with row number reporting
        row_number = 1  # Start at 1 for header row
        for row in reader:
            row_number += 1
            
            # Skip completed assignments
            if row.get("status", "").strip().lower() == "complete":
                continue
            
            # Date parsing with error handling
            try:
                due = datetime.strptime(row["due_date"].strip(), "%Y-%m-%d").date()
            except ValueError:
                return f"Invalid date format in row {row_number}: {row['due_date']}. Expected YYYY-MM-DD"
            except KeyError:
                return f"Invalid date format in row {row_number}: . Expected YYYY-MM-DD"
```

**What's happening here:**
- **row_number tracking**: Keep track of which row we're processing for error messages
- **Skip complete assignments**: Filter out assignments with status "complete" (case-insensitive)
- **Date parsing**: Convert the due_date string to a Python date object
  - `strip()` removes whitespace
  - `strptime()` parses the date string using the YYYY-MM-DD format
  - `.date()` extracts just the date part (no time)
- **Error handling**: If date parsing fails, return a descriptive error with the row number

### 3.10 Step 5: Handle Estimated Hours

Add logic to handle numeric and non-numeric hours:

```python
            # Graceful handling for invalid estimated_hours values
            hours_str = row.get("estimated_hours", "").strip()
            try:
                hours = float(hours_str)
                hours_display = f"{hours_str}h"
            except ValueError:
                hours = 0.0  # Default to 0 for priority calculation
                hours_display = "?h"
```

**What's happening here:**
- Try to convert estimated_hours to a float
- If successful, use the original string for display (preserves "3" vs "3.0")
- If conversion fails (non-numeric value), use "?" for display and 0.0 for calculations
- This graceful degradation prevents the tool from crashing on invalid data

### 3.11 Step 6: Calculate Priority and Format Entry

Add priority calculation and formatting:

```python
            # Calculate days remaining and priority score
            days_remaining = (due - today).days
            priority_score = calculate_priority_score(days_remaining, hours, 
                                                     days_until_due_weight, effort_weight)
            
            # Format the assignment entry
            entry = (
                f"  [{row['course']}] {row['assignment']}"
                f" — due {due.strftime('%a %b %d')}"
                f" ({row['type']}, ~{hours_display}, {row['status']})"
            )
            
            # Add notes if present
            if row.get("notes", "").strip():
                entry += f"\n    Note: {row['notes'].strip()}"
```

**What's happening here:**
- **days_remaining**: Calculate how many days until the due date (can be negative for overdue)
- **priority_score**: Use the helper function to calculate priority
- **Format entry**: Create a formatted string with all assignment details
  - `[CSCE 350] HW5 - Dynamic Programming — due Thu Apr 09 (homework, ~3h, not started)`
  - Date formatted as "Day Mon DD" (e.g., "Thu Apr 09")
- **Add notes**: If notes exist, add them on an indented line below

### 3.12 Step 7: Categorize into Buckets

Add bucket categorization logic:

```python
            # Store as tuple: (priority_score, entry) for sorting
            if due < today:
                buckets["overdue"].append((priority_score, entry))
            elif due == today:
                buckets["due_today"].append((priority_score, entry))
            elif due <= week_end:
                buckets["due_this_week"].append((priority_score, entry))
            else:
                buckets["upcoming"].append((priority_score, entry))
```

**What's happening here:**
- **Bucket logic**: Compare due date to today and week_end to determine category
  - `due < today`: Overdue (deadline has passed)
  - `due == today`: Due today (deadline is today)
  - `due <= week_end`: Due this week (after today but before week ends)
  - `else`: Upcoming (after this week)
- **Store as tuple**: Save both the priority_score and the formatted entry for sorting

### 3.13 Step 8: Sort Buckets by Priority

Add sorting logic after the loop:

```python
        # Sort each bucket by priority score (lower score = higher priority)
        for bucket_key in buckets:
            buckets[bucket_key].sort(key=lambda x: x[0])
            # Extract just the entry strings after sorting
            buckets[bucket_key] = [entry for _, entry in buckets[bucket_key]]
```

**What's happening here:**
- **Sort by priority**: For each bucket, sort assignments by their priority score
  - `key=lambda x: x[0]` means sort by the first element of the tuple (priority_score)
  - Lower scores appear first (higher priority)
- **Extract entries**: After sorting, extract just the formatted strings (discard scores)

### 3.14 Step 9: Format Final Output

Add output formatting:

```python
        # Format output with proper headers and bucket counts
        lines = [f"Today: {today.strftime('%a %b %d')}  |  Week ends: {week_end.strftime('%a %b %d')}\n"]
        
        for key, items in buckets.items():
            bucket_name = key.replace('_', ' ').upper()
            lines.append(f"{bucket_name} ({len(items)})")
            lines += items if items else ["  (none)"]
            lines.append("")

        return "\n".join(lines)
```

**What's happening here:**
- **Header line**: Show today's date and when the week ends
- **For each bucket**:
  - Convert key to title (e.g., "due_today" → "DUE TODAY")
  - Show bucket name with count: "DUE TODAY (3)"
  - List assignments, or "(none)" if empty
  - Add blank line for spacing
- **Join lines**: Combine all lines into a single string with newlines

### 3.15 Step 10: Add Error Handling and Cleanup

Add final error handling and file cleanup:

```python
    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()
```

**What's happening here:**
- **csv.Error**: Catch any CSV parsing errors and return a descriptive message
- **finally block**: Always close the file, even if an error occurs
- This ensures proper resource cleanup

### 3.16 Update Your Agent to Use the New Tool

Update your agent creation to include the new tool:

```python
# Create the agent with both tools
agent = Agent(
    model=model,
    system_prompt=load_system_prompt(),
    tools=[load_assignments, web_search],  # Add load_assignments here
)
```

**What's happening here:**
- Add `load_assignments` to the tools list
- The agent can now use both the custom tool and web_search
- The agent will automatically decide when to call each tool based on the user's request

### 3.17 Test Your Custom Tool

Update the test code at the bottom of your file:

```python
if __name__ == "__main__":
    agent("""Give me my daily briefing.
        My assignments file is 'assignments.csv'.""")
```

Run your agent:

```bash
python agent.py
```

**Expected Output:**

You should see a structured daily briefing with five sections:

```
SITUATION — Heavy week with 4 assignments due and multiple exams coming up

TODAY — 
• [MATH 251] Quiz 4 Preparation — due Tue Apr 08 (exam, ~1.5h, not started)
    Note: Covers sections 6.1-6.3
• [ENGL 101] Peer Review Comments — due Tue Apr 08 (homework, ~0.5h, not started)
    Note: Review 2 classmates' essays

THIS WEEK —
Monday: 2h MATH 251 quiz prep, 0.5h ENGL peer reviews
Tuesday: 3h CSCE 350 HW5, 1h HIST reading notes
Wednesday: 2.5h ENGL essay draft
Thursday: 2h CSCE 350 lab, 3.5h MATH exam study guide
Friday: 4h PHYS problem set, 5h CSCE project milestone
Saturday: (catch-up buffer)
Sunday: (rest and plan next week)

HEADS UP — Nothing due next week yet, but stay ahead on readings

TIP — For dynamic programming problems, start by identifying overlapping subproblems. Draw out the recursion tree to visualize where memoization will help.
```

**Note:** The actual output will vary based on:
- Today's date (affects bucket categorization)
- Your CSV content
- What the LLM generates for the briefing

### 3.18 Understanding the Tool Workflow

Let's trace what happens when you invoke the agent:

1. **User invokes agent**: "Give me my daily briefing. My assignments file is 'assignments.csv'."
2. **Agent reads system prompt**: Understands it should generate a five-section briefing
3. **Agent sees load_assignments tool**: Reads the docstring to understand what it does
4. **Agent decides to call the tool**: Recognizes it needs assignment data
5. **Tool executes**:
   - Opens assignments.csv
   - Validates columns
   - Parses each row
   - Filters out completed assignments
   - Categorizes by due date
   - Calculates priority scores
   - Sorts within buckets
   - Formats output
6. **Tool returns formatted text**: Structured assignment data
7. **Agent sends to LLM**: System prompt + tool output → Bedrock
8. **LLM generates briefing**: Creates the five-section structure
9. **Agent returns result**: You see the final briefing

### 3.19 Testing with Different CSV Files

The workshop includes several example CSV files for testing. Try them:

**Test with current week assignments:**
```python
agent("Give me my daily briefing. My assignments file is 'examples/current_week_assignments.csv'.")
```

**Test with overdue assignments:**
```python
agent("Give me my daily briefing. My assignments file is 'examples/overdue_assignments.csv'.")
```

**Test with mixed deadlines:**
```python
agent("Give me my daily briefing. My assignments file is 'examples/mixed_assignments.csv'.")
```

**Test error handling:**
```python
# File not found
agent("Give me my daily briefing. My assignments file is 'nonexistent.csv'.")

# Invalid date format
agent("Give me my daily briefing. My assignments file is 'examples/invalid_dates.csv'.")

# Missing columns
agent("Give me my daily briefing. My assignments file is 'examples/missing_columns.csv'.")
```

### 3.20 Understanding Priority Scores

Let's see how priority scores work with examples:

**Example 1: Urgency vs. Effort**
- Assignment A: Due in 1 day, 5 hours → Score = (2.0 × 1) + (1.0 × 5) = 7.0
- Assignment B: Due in 2 days, 2 hours → Score = (2.0 × 2) + (1.0 × 2) = 6.0
- **Result**: B appears first (lower score = higher priority) despite A having more hours

**Example 2: Same Due Date**
- Assignment A: Due in 3 days, 2 hours → Score = (2.0 × 3) + (1.0 × 2) = 8.0
- Assignment B: Due in 3 days, 4 hours → Score = (2.0 × 3) + (1.0 × 4) = 10.0
- **Result**: A appears first (less effort, same deadline)

**Example 3: Overdue Assignments**
- Assignment A: Due 2 days ago, 3 hours → Score = (2.0 × -2) + (1.0 × 3) = -1.0
- Assignment B: Due 1 day ago, 1 hour → Score = (2.0 × -1) + (1.0 × 1) = -1.0
- **Result**: A appears first (more overdue)

**Customizing Weights:**

You can adjust the priority calculation by changing the weights:

```python
# Emphasize urgency more (default)
agent("Give me my daily briefing. My assignments file is 'assignments.csv'.")

# Emphasize effort more
# (You would need to modify the agent invocation to pass custom weights)
```

### 3.21 Customizing Your System Prompt (Optional)

Experiment with different agent personalities by modifying `system_prompt.txt`:

**Formal Academic Advisor:**
```
You are a professional academic advisor providing a structured daily briefing.

Your response must contain exactly five sections:

SITUATION — A formal assessment of the student's current academic workload

TODAY — A prioritized list of tasks requiring immediate attention today

THIS WEEK — A detailed time-blocked schedule from Monday through Sunday, allocating specific hours to each assignment based on estimated_hours

HEADS UP — Advance notice of upcoming assignments that require early preparation

TIP — One evidence-based study strategy relevant to the current workload

Maintain a professional, supportive tone. Be thorough and precise.
```

**Casual Peer Mentor:**
```
You're a chill upperclassman helping a friend plan their week.

Hit them with:

SITUATION — Real talk about how packed this week is

TODAY — What needs to get done today, no excuses

THIS WEEK — Break down the week day by day, keep it realistic

HEADS UP — Stuff coming up they should start thinking about

TIP — One solid study hack that actually works

Keep it friendly and real. No corporate speak.
```

Try different prompts and see how the agent's tone and style change!

### 3.22 Stage Two Complete!

Congratulations! You've built a custom tool and integrated it into your agent. You now understand:
- How to use the `@tool` decorator to create custom tools
- How to parse and validate CSV data with proper error handling
- How to implement date-based categorization logic
- How to calculate and use priority scores
- How to format structured output for agent consumption
- How to test your tool with various inputs

**Key Takeaways:**
- **Tools extend agent capabilities**: Custom tools let agents interact with external data sources
- **Error handling is critical**: Descriptive error messages help users fix issues quickly
- **Structured output matters**: Well-formatted tool output helps the LLM generate better responses
- **Testing is essential**: Test with various inputs to ensure robustness

**Next Steps:**
- Experiment with different CSV files and assignments
- Customize the priority score weights for your preferences
- Modify the system prompt to change the agent's personality
- Add more custom tools (e.g., calendar integration, grade tracking)
- Deploy your agent to AWS Agent Core Service (see deployment guide)

You now have a fully functional Academic Advisor Agent that provides personalized daily briefings based on your actual coursework!
