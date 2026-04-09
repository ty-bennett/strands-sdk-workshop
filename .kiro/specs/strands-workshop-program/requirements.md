# Requirements Document

## Introduction

The Strands Workshop Program is an educational workshop system that teaches students how to create AI agents using the Strands SDK. The workshop progresses through two stages: first building a simple agent that uses pre-built tools, then enhancing it with custom tools. The centerpiece is an Academic Advisor Agent that helps students manage their coursework by reading assignment data from CSV files, analyzing deadlines and workload, and generating prioritized daily briefings with time-blocked schedules.

The system integrates with AWS Bedrock for LLM capabilities and uses AWS infrastructure (Agent Core Service and supporting services) to host and run the agents. Students work in Python virtual environments and learn practical agent development skills through hands-on exercises.

## Glossary

- **Workshop_System**: The complete educational program including materials, infrastructure, and exercises
- **Academic_Advisor_Agent**: The AI agent that provides daily briefings and assignment prioritization
- **Assignment_Tracker_Tool**: Custom tool that reads CSV files, parses assignment data, and generates prioritized to-do lists
- **Agent_Core_Service**: AWS service that hosts and executes the student agents
- **Strands_SDK**: The software development kit used to build agents (strands-agents library)
- **Workshop_Guide**: Documentation that provides setup instructions and exercise walkthroughs
- **Assignment_CSV**: CSV file containing student assignment data with fields: course, assignment, due_date, type, estimated_hours, status, notes
- **Daily_Briefing**: Structured output from the agent containing situation summary, today's tasks, weekly schedule, upcoming items, and study tips
- **Stage_One_Exercise**: Workshop exercise where students build a simple agent using pre-built tools
- **Stage_Two_Exercise**: Workshop exercise where students add custom assignment tracking tool
- **AWS_Bedrock**: Amazon Web Services managed service providing access to foundation models
- **Priority_Score**: Calculated value combining deadline urgency and estimated effort to rank assignments
- **Time_Block_Plan**: Day-by-day schedule allocating specific hours to assignments based on estimated_hours

## Requirements

### Requirement 1: Workshop Structure and Progression

**User Story:** As a workshop instructor, I want a two-stage progressive curriculum, so that students learn agent fundamentals before building custom tools

#### Acceptance Criteria

1. THE Workshop_System SHALL provide exactly two sequential exercises: Stage_One_Exercise and Stage_Two_Exercise
2. THE Stage_One_Exercise SHALL teach agent creation using only pre-built tools from strands-agents-tools
3. THE Stage_Two_Exercise SHALL teach custom tool development by adding Assignment_Tracker_Tool
4. WHEN a student completes Stage_One_Exercise, THE Workshop_System SHALL provide clear transition instructions to Stage_Two_Exercise
5. THE Workshop_Guide SHALL document learning objectives for each stage separately

### Requirement 2: Python Environment Setup

**User Story:** As a student, I want clear environment setup instructions, so that I can prepare my development environment correctly

#### Acceptance Criteria

1. THE Workshop_Guide SHALL specify Python 3.12 or higher as the minimum version requirement
2. THE Workshop_Guide SHALL provide commands for creating a virtual environment on both Unix and Windows systems
3. THE Workshop_Guide SHALL provide the command to install dependencies from requirements.txt
4. THE Workshop_System SHALL include a requirements.txt file listing strands-agents and strands-agents-tools
5. WHEN a student follows the setup instructions, THE Workshop_System SHALL result in a working Python environment with all dependencies installed

### Requirement 3: AWS Bedrock Integration

**User Story:** As a student, I want to connect my agent to AWS Bedrock, so that it can use Claude Sonnet 4.5 for language understanding

#### Acceptance Criteria

1. THE Workshop_Guide SHALL document how to configure AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION environment variables
2. THE Academic_Advisor_Agent SHALL use BedrockModel with model_id "us.anthropic.claude-sonnet-4-5"
3. WHEN AWS credentials are invalid or missing, THE Academic_Advisor_Agent SHALL return a descriptive error message indicating the authentication failure
4. THE Workshop_Guide SHALL provide instructions for obtaining AWS Bedrock access keys
5. WHEN the agent makes a request to AWS Bedrock, THE Academic_Advisor_Agent SHALL handle rate limiting errors gracefully

### Requirement 4: Assignment CSV Format and Parsing

**User Story:** As a student, I want to store my assignments in a CSV file, so that the agent can read and analyze my workload

#### Acceptance Criteria

1. THE Assignment_CSV SHALL contain the following required fields: course, assignment, due_date, type, estimated_hours, status, notes
2. THE Assignment_Tracker_Tool SHALL parse due_date fields in YYYY-MM-DD format
3. WHEN a due_date field contains an invalid date format, THE Assignment_Tracker_Tool SHALL return an error message identifying the invalid row
4. THE Assignment_Tracker_Tool SHALL treat assignments with status "complete" as completed and exclude them from active workload
5. THE Assignment_Tracker_Tool SHALL handle empty or missing notes fields without errors
6. THE Workshop_System SHALL provide an example Assignment_CSV with at least 10 sample assignments covering various courses, types, and deadlines

### Requirement 5: Assignment Prioritization Logic

**User Story:** As a student, I want my assignments prioritized by urgency and effort, so that I focus on the most critical work first

#### Acceptance Criteria

1. THE Assignment_Tracker_Tool SHALL categorize assignments into exactly four buckets: overdue, due_today, due_this_week, and upcoming
2. WHEN an assignment due_date is before today's date, THE Assignment_Tracker_Tool SHALL place it in the overdue bucket
3. WHEN an assignment due_date equals today's date, THE Assignment_Tracker_Tool SHALL place it in the due_today bucket
4. WHEN an assignment due_date is after today but on or before the end of the current week (Sunday), THE Assignment_Tracker_Tool SHALL place it in the due_this_week bucket
5. WHEN an assignment due_date is after the current week ends, THE Assignment_Tracker_Tool SHALL place it in the upcoming bucket
6. WITHIN each bucket, THE Assignment_Tracker_Tool SHALL sort assignments by Priority_Score calculated as: (days_until_due_weight * days_remaining) + (effort_weight * estimated_hours)
7. THE Assignment_Tracker_Tool SHALL use configurable weights for days_until_due_weight and effort_weight with defaults of 2.0 and 1.0 respectively

### Requirement 6: Daily Briefing Generation

**User Story:** As a student, I want a structured daily briefing, so that I understand my workload and have a clear action plan

#### Acceptance Criteria

1. THE Academic_Advisor_Agent SHALL generate a Daily_Briefing with exactly five sections: SITUATION, TODAY, THIS WEEK, HEADS UP, and TIP
2. THE SITUATION section SHALL contain one sentence summarizing the overall workload intensity
3. THE TODAY section SHALL list tasks due today in priority order as bullet points
4. THE THIS WEEK section SHALL provide a Time_Block_Plan showing day-by-day task allocation from Monday through Sunday
5. THE Time_Block_Plan SHALL allocate time to each assignment based on its estimated_hours field
6. THE HEADS UP section SHALL identify assignments due next week that should be started now
7. THE TIP section SHALL provide one actionable study tip relevant to the current workload
8. THE Academic_Advisor_Agent SHALL use the system prompt from system_prompt.txt to format the Daily_Briefing

### Requirement 7: Custom Tool Development

**User Story:** As a student, I want to create a custom tool using the @tool decorator, so that I learn how to extend agent capabilities

#### Acceptance Criteria

1. THE Stage_Two_Exercise SHALL guide students to implement Assignment_Tracker_Tool using the @tool decorator from Strands_SDK
2. THE Assignment_Tracker_Tool SHALL accept a filepath parameter of type string
3. THE Assignment_Tracker_Tool SHALL return a formatted string containing categorized and prioritized assignments
4. WHEN the filepath parameter points to a non-existent file, THE Assignment_Tracker_Tool SHALL return an error message indicating the file was not found
5. WHEN the CSV file is malformed or missing required columns, THE Assignment_Tracker_Tool SHALL return an error message identifying the specific parsing issue
6. THE Workshop_Guide SHALL provide a complete reference implementation of Assignment_Tracker_Tool

### Requirement 8: Agent Core Service Deployment

**User Story:** As a student, I want to deploy my agent to AWS, so that it runs in the cloud and can be accessed remotely

#### Acceptance Criteria

1. THE Workshop_Guide SHALL document the process for deploying Academic_Advisor_Agent to Agent_Core_Service
2. THE Workshop_System SHALL provide infrastructure-as-code templates for provisioning Agent_Core_Service and supporting AWS services
3. WHEN a student deploys their agent, THE Agent_Core_Service SHALL host the agent and make it accessible via API endpoint
4. THE Workshop_Guide SHALL document how to invoke the deployed agent using HTTP requests
5. WHEN the agent is invoked via Agent_Core_Service, THE Academic_Advisor_Agent SHALL execute with the same behavior as local execution
6. THE Workshop_System SHALL include monitoring and logging configuration for deployed agents using AWS CloudWatch

### Requirement 9: Web Search Tool Integration

**User Story:** As a student, I want my agent to search the web for study tips, so that it provides relevant and current advice

#### Acceptance Criteria

1. THE Academic_Advisor_Agent SHALL include web_search tool from strands-agents-tools in its tools list
2. WHEN generating the TIP section, THE Academic_Advisor_Agent SHALL use web_search if subject-specific advice would be helpful
3. WHEN web_search is unavailable or returns an error, THE Academic_Advisor_Agent SHALL generate a TIP without web search rather than failing
4. THE Workshop_Guide SHALL explain when and how the agent uses web_search tool
5. THE Stage_One_Exercise SHALL demonstrate web_search usage before students build custom tools

### Requirement 10: Workshop Materials and Documentation

**User Story:** As an instructor, I want comprehensive workshop materials, so that I can effectively teach the workshop

#### Acceptance Criteria

1. THE Workshop_System SHALL provide a Workshop_Guide with setup instructions, exercise walkthroughs, and troubleshooting tips
2. THE Workshop_System SHALL include presentation slides covering agent concepts, Strands_SDK architecture, and AWS integration
3. THE Workshop_System SHALL provide solution code for both Stage_One_Exercise and Stage_Two_Exercise
4. THE Workshop_Guide SHALL include a troubleshooting section addressing common errors: missing dependencies, AWS authentication failures, CSV parsing errors, and deployment issues
5. THE Workshop_System SHALL provide a sample Assignment_CSV file that students can use for testing
6. THE Workshop_Guide SHALL estimate 2-3 hours total workshop duration with time breakdowns per section

### Requirement 11: Error Handling and Validation

**User Story:** As a student, I want clear error messages when something goes wrong, so that I can debug issues quickly

#### Acceptance Criteria

1. WHEN AWS credentials are missing, THE Academic_Advisor_Agent SHALL return an error message stating "AWS credentials not configured. Please set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION"
2. WHEN the Assignment_CSV file is not found, THE Assignment_Tracker_Tool SHALL return an error message stating "Assignment file not found: {filepath}"
3. WHEN the Assignment_CSV is missing required columns, THE Assignment_Tracker_Tool SHALL return an error message listing the missing column names
4. WHEN a due_date cannot be parsed, THE Assignment_Tracker_Tool SHALL return an error message stating "Invalid date format in row {row_number}: {due_date_value}. Expected YYYY-MM-DD"
5. WHEN estimated_hours is not a valid number, THE Assignment_Tracker_Tool SHALL treat it as unknown and display "?" in the output
6. THE Workshop_Guide SHALL document all error messages and their resolutions

### Requirement 12: Testing and Validation Data

**User Story:** As a student, I want test data and examples, so that I can verify my agent works correctly

#### Acceptance Criteria

1. THE Workshop_System SHALL provide at least three example Assignment_CSV files: one with current week assignments, one with overdue items, and one with mixed deadlines
2. THE Workshop_System SHALL provide expected Daily_Briefing outputs for each example Assignment_CSV
3. THE Workshop_Guide SHALL include a testing section with steps to verify agent behavior
4. THE Workshop_System SHALL provide a validation script that checks Assignment_CSV format correctness
5. WHEN a student runs their agent with the provided test data, THE Academic_Advisor_Agent SHALL produce output matching the expected format structure

### Requirement 13: Assignment Data Formatting

**User Story:** As a student, I want my assignment data displayed clearly, so that I can quickly understand my workload

#### Acceptance Criteria

1. THE Assignment_Tracker_Tool SHALL format each assignment as: "[{course}] {assignment} — due {formatted_date} ({type}, ~{estimated_hours}h, {status})"
2. THE Assignment_Tracker_Tool SHALL format dates in the output as "Day Mon DD" format (e.g., "Mon Jan 15")
3. WHEN an assignment has notes, THE Assignment_Tracker_Tool SHALL display them indented below the assignment as "Note: {notes}"
4. THE Assignment_Tracker_Tool SHALL display the current date and week end date at the top of the output
5. THE Assignment_Tracker_Tool SHALL display a count of assignments in each bucket as "{BUCKET_NAME} ({count})"
6. WHEN a bucket contains no assignments, THE Assignment_Tracker_Tool SHALL display "(none)" for that bucket

### Requirement 14: Infrastructure as Code

**User Story:** As an instructor, I want automated infrastructure provisioning, so that students can deploy without manual AWS console configuration

#### Acceptance Criteria

1. THE Workshop_System SHALL provide AWS CloudFormation or Terraform templates for all required infrastructure
2. THE infrastructure templates SHALL provision Agent_Core_Service, AWS Bedrock access, IAM roles, and CloudWatch logging
3. THE Workshop_Guide SHALL document the infrastructure deployment process with step-by-step commands
4. WHEN infrastructure templates are applied, THE Workshop_System SHALL create all resources with appropriate security configurations
5. THE infrastructure templates SHALL include resource tagging for workshop identification and cost tracking
6. THE Workshop_Guide SHALL document the infrastructure teardown process to avoid ongoing AWS costs

### Requirement 15: System Prompt Configuration

**User Story:** As a student, I want to customize the agent's personality, so that I can experiment with different briefing styles

#### Acceptance Criteria

1. THE Academic_Advisor_Agent SHALL load its system prompt from system_prompt.txt file
2. THE Workshop_Guide SHALL explain the structure and purpose of the system prompt
3. THE Stage_Two_Exercise SHALL include an optional activity to modify the system prompt and observe behavior changes
4. WHEN system_prompt.txt is missing, THE Academic_Advisor_Agent SHALL return an error message indicating the file is required
5. THE Workshop_System SHALL provide at least two alternative system prompt examples: one formal academic advisor and one casual peer mentor

## Correctness Properties

### Property 1: Assignment Categorization Completeness

**Property Type:** Invariant

**Description:** Every non-complete assignment must be placed in exactly one bucket

**Formal Statement:** For all assignments in Assignment_CSV where status ≠ "complete", the assignment appears in exactly one of {overdue, due_today, due_this_week, upcoming}

**Test Approach:** Property-based test that generates random Assignment_CSV files with various dates and verifies each non-complete assignment appears in exactly one bucket

### Property 2: Date Bucket Boundaries

**Property Type:** Invariant

**Description:** Assignment bucket placement must respect date boundaries

**Formal Statement:** 
- If due_date < today, then assignment ∈ overdue
- If due_date = today, then assignment ∈ due_today  
- If today < due_date ≤ week_end, then assignment ∈ due_this_week
- If due_date > week_end, then assignment ∈ upcoming

**Test Approach:** Property-based test that generates assignments with dates relative to a fixed "today" and verifies correct bucket placement

### Property 3: CSV Parse-Format Round Trip

**Property Type:** Round Trip

**Description:** Parsing a valid CSV and formatting the output should preserve all assignment data

**Formal Statement:** For all valid Assignment_CSV files, parse(csv) → format(assignments) should contain all non-complete assignment information from the original CSV

**Test Approach:** Property-based test that generates valid CSV data, parses it, formats the output, and verifies all assignment fields are present in the formatted string

### Property 4: Priority Score Monotonicity

**Property Type:** Metamorphic

**Description:** Within a bucket, assignments with higher priority scores should appear before those with lower scores

**Formal Statement:** For all assignments A and B in the same bucket, if Priority_Score(A) > Priority_Score(B), then A appears before B in the output

**Test Approach:** Property-based test that generates assignments with varying estimated_hours and due_dates, then verifies the output ordering matches priority score ordering

### Property 5: Time Block Allocation Conservation

**Property Type:** Invariant

**Description:** The sum of hours allocated in the Time_Block_Plan should equal the sum of estimated_hours for all assignments due this week

**Formal Statement:** Σ(hours in Time_Block_Plan) = Σ(estimated_hours for assignments in due_today ∪ due_this_week)

**Test Approach:** Property-based test that generates assignments due within the current week and verifies the total hours allocated matches the sum of estimated_hours

### Property 6: Error Message Determinism

**Property Type:** Invariant

**Description:** The same error condition should always produce the same error message

**Formal Statement:** For all error conditions E, error_message(E) is deterministic and consistent across invocations

**Test Approach:** Example-based test that triggers each documented error condition multiple times and verifies identical error messages

### Property 7: Bucket Count Accuracy

**Property Type:** Invariant

**Description:** The displayed count for each bucket must match the actual number of assignments in that bucket

**Formal Statement:** For each bucket B, displayed_count(B) = |assignments in B|

**Test Approach:** Property-based test that generates random Assignment_CSV files and verifies the count displayed in the output matches the actual number of assignments parsed into each bucket

### Property 8: Date Format Consistency

**Property Type:** Invariant

**Description:** All dates in the output must follow the same format pattern

**Formal Statement:** For all dates D in the formatted output, D matches the pattern "Day Mon DD" (e.g., "Mon Jan 15")

**Test Approach:** Property-based test that generates assignments with various dates and uses regex to verify all formatted dates match the expected pattern

### Property 9: Complete Assignment Exclusion

**Property Type:** Invariant

**Description:** Assignments marked as complete should never appear in any bucket

**Formal Statement:** For all assignments A where status = "complete", A ∉ (overdue ∪ due_today ∪ due_this_week ∪ upcoming)

**Test Approach:** Property-based test that generates Assignment_CSV files with mix of complete and incomplete assignments, verifies complete assignments are absent from all buckets

### Property 10: Daily Briefing Structure Completeness

**Property Type:** Invariant

**Description:** Every Daily_Briefing must contain all five required sections

**Formal Statement:** For all Daily_Briefing outputs B, B contains exactly one instance of each: SITUATION, TODAY, THIS WEEK, HEADS UP, TIP

**Test Approach:** Example-based test with various Assignment_CSV inputs that parses the Daily_Briefing output and verifies all five section headers are present exactly once

### Property 11: AWS Credential Validation Idempotence

**Property Type:** Idempotence

**Description:** Checking AWS credentials multiple times with the same configuration should produce the same result

**Formal Statement:** For all credential configurations C, validate_credentials(C) = validate_credentials(validate_credentials(C))

**Test Approach:** Example-based test that validates credentials with both valid and invalid configurations multiple times and verifies consistent results

### Property 12: File Path Error Consistency

**Property Type:** Invariant

**Description:** Non-existent file paths should always produce file-not-found errors

**Formal Statement:** For all non-existent file paths P, Assignment_Tracker_Tool(P) returns error message containing "not found" and P

**Test Approach:** Property-based test that generates random non-existent file paths and verifies the error message format and content
