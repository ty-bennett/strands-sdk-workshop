# Implementation Plan: Strands Workshop Program

## Overview

This implementation plan builds a complete educational workshop system for teaching AI agent development using the Strands SDK and AWS Bedrock. The system includes workshop materials (guide, slides, examples), a fully-featured Assignment Tracker Tool with CSV parsing and prioritization, an Academic Advisor Agent with error handling and validation, AWS infrastructure templates, and a comprehensive property-based testing suite.

The implementation follows a progressive approach: first enhancing existing files with error handling and validation, then creating workshop materials and example data, implementing the property-based test suite, building AWS infrastructure templates, and finally creating deployment automation.

## Tasks

- [ ] 1. Enhance Assignment Tracker Tool with error handling and validation
  - [x] 1.1 Add comprehensive error handling to load_assignments function
    - Implement FileNotFoundError handling with descriptive message
    - Add CSV column validation with missing column reporting
    - Implement date parsing error handling with row number reporting
    - Add graceful handling for invalid estimated_hours values
    - Handle malformed CSV files with specific error messages
    - _Requirements: 4.3, 7.2, 7.4, 7.5, 11.2, 11.3, 11.4, 11.5_
  
  - [x] 1.2 Implement priority score calculation and sorting
    - Add priority_score calculation function with configurable weights
    - Set default weights: days_until_due_weight=2.0, effort_weight=1.0
    - Sort assignments within each bucket by priority score
    - _Requirements: 5.6, 5.7_
  
  - [x] 1.3 Improve output formatting to match specification
    - Update date formatting to "Day Mon DD" format
    - Add header with current date and week end date
    - Display bucket counts with "(none)" for empty buckets
    - Format notes with proper indentation
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_
  
  - [ ]* 1.4 Write property tests for Assignment Tracker Tool
    - **Property 1: Assignment Bucket Categorization by Date**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
  
  - [ ]* 1.5 Write property test for complete assignment exclusion
    - **Property 2: Complete Assignment Exclusion**
    - **Validates: Requirements 4.4**
  
  - [ ]* 1.6 Write property test for priority score ordering
    - **Property 3: Priority Score Ordering Within Buckets**
    - **Validates: Requirements 5.6**

- [ ] 2. Enhance Academic Advisor Agent with validation and configuration
  - [x] 2.1 Add AWS credentials validation
    - Create validate_aws_credentials() function
    - Check for AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    - Return descriptive error message matching specification
    - Call validation before creating BedrockModel
    - _Requirements: 3.3, 11.1_
  
  - [x] 2.2 Implement system prompt loading from file
    - Create load_system_prompt() function
    - Handle FileNotFoundError with descriptive message
    - Replace hardcoded system prompt with file loading
    - _Requirements: 6.8, 15.1, 15.4_
  
  - [x] 2.3 Add rate limiting and retry logic for Bedrock
    - Implement invoke_with_retry() function with exponential backoff
    - Handle ThrottlingException from Bedrock API
    - Set max_retries=3 with 2^attempt wait time
    - _Requirements: 3.5_
  
  - [ ]* 2.4 Write property test for AWS credential validation
    - **Property 21: AWS Credential Error Descriptiveness**
    - **Validates: Requirements 3.3**
  
  - [ ]* 2.5 Write unit tests for agent configuration
    - Test model_id configuration
    - Test system prompt loading
    - Test tools list includes load_assignments and web_search
    - _Requirements: 3.2, 9.1_

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Create example CSV files and test data
  - [x] 4.1 Create current_week_assignments.csv
    - Include 8-10 assignments all due within current week
    - Mix of different courses, types, and estimated hours
    - All assignments with status "not started" or "in progress"
    - _Requirements: 12.1_
  
  - [x] 4.2 Create overdue_assignments.csv
    - Include 5-6 overdue assignments
    - Include 4-5 current week assignments
    - Mix of statuses including some "complete"
    - _Requirements: 12.1_
  
  - [x] 4.3 Create mixed_assignments.csv
    - Include assignments in all four buckets (overdue, today, this week, upcoming)
    - Include at least 15 total assignments
    - Include edge cases: empty notes, various estimated_hours values
    - _Requirements: 4.6, 12.1_
  
  - [x] 4.4 Create edge_cases.csv for testing
    - Include empty notes fields
    - Include non-numeric estimated_hours values
    - Include special characters in assignment names
    - Include boundary dates (today, week_end, week_end+1)
    - _Requirements: 4.5, 11.5_
  
  - [x] 4.5 Create invalid test files for error testing
    - Create invalid_dates.csv with various invalid date formats
    - Create missing_columns.csv without required columns
    - Create nonexistent_file reference for FileNotFoundError testing
    - _Requirements: 11.2, 11.3, 11.4_
  
  - [ ]* 4.6 Write property tests for CSV parsing
    - **Property 4: CSV Column Validation**
    - **Validates: Requirements 4.1, 11.3**
  
  - [ ]* 4.7 Write property tests for date handling
    - **Property 5: Date Parsing Round Trip**
    - **Property 6: Invalid Date Error Reporting**
    - **Validates: Requirements 4.2, 4.3, 11.4**

- [ ] 5. Expand workshop guide with comprehensive documentation
  - [x] 5.1 Enhance setup section with detailed instructions
    - Add Python version verification commands
    - Add virtual environment creation for Unix and Windows
    - Add dependency installation steps
    - Add AWS credentials configuration instructions
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.4_
  
  - [x] 5.2 Create Stage One exercise walkthrough
    - Document creating basic agent with web_search tool
    - Provide step-by-step code examples
    - Explain agent invocation and testing
    - Include expected output examples
    - _Requirements: 1.2, 9.5_
  
  - [x] 5.3 Create Stage Two exercise walkthrough
    - Document adding @tool decorator to create custom tool
    - Provide step-by-step implementation of load_assignments
    - Explain CSV parsing and bucket categorization logic
    - Include testing instructions with example CSVs
    - _Requirements: 1.3, 7.1, 7.2, 7.3_
  
  - [ ] 5.4 Add AWS deployment section
    - Document Agent Core Service deployment process
    - Provide infrastructure deployment commands
    - Explain HTTP API invocation
    - Include monitoring and logging instructions
    - _Requirements: 8.1, 8.3, 8.4, 8.6_
  
  - [ ] 5.5 Create troubleshooting section
    - Document common errors and resolutions
    - Include all error messages from requirements
    - Add debugging tips for each error type
    - _Requirements: 10.4, 11.6_
  
  - [ ] 5.6 Add learning objectives and time estimates
    - Document Stage One and Stage Two learning objectives
    - Provide time estimates for each section
    - Add transition instructions between stages
    - _Requirements: 1.4, 1.5, 10.6_

- [ ] 6. Create alternative system prompts and configuration examples
  - [ ] 6.1 Create formal_advisor.txt system prompt
    - Write formal academic advisor personality
    - Maintain five-section structure
    - Use professional, detailed language
    - _Requirements: 15.5_
  
  - [ ] 6.2 Create casual_mentor.txt system prompt
    - Write casual peer mentor personality
    - Maintain five-section structure
    - Use friendly, conversational language
    - _Requirements: 15.5_
  
  - [ ] 6.3 Add system prompt customization section to guide
    - Explain system prompt structure and purpose
    - Document how to modify and experiment with prompts
    - Include optional Stage Two activity for prompt customization
    - _Requirements: 15.2, 15.3_

- [ ] 7. Implement comprehensive property-based test suite
  - [ ] 7.1 Set up testing infrastructure
    - Create tests/ directory structure
    - Configure pytest with hypothesis plugin
    - Set hypothesis min_iterations=100
    - Create test fixtures for CSV generation
    - Add pytest markers: property, unit, integration
    - _Requirements: Testing Strategy_
  
  - [ ] 7.2 Write property tests for error handling
    - **Property 8: File Not Found Error Format**
    - **Property 9: Invalid Estimated Hours Handling**
    - **Property 19: Malformed CSV Error Reporting**
    - **Validates: Requirements 7.4, 7.5, 11.2, 11.5_
  
  - [ ] 7.3 Write property tests for output formatting
    - **Property 10: Assignment Format Consistency**
    - **Property 11: Notes Display Format**
    - **Property 12: Bucket Count Accuracy**
    - **Property 13: Output Header Presence**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6**
  
  - [ ] 7.4 Write property tests for Daily Briefing structure
    - **Property 14: Daily Briefing Structure Completeness**
    - **Property 15: Today's Tasks in TODAY Section**
    - **Property 16: Week Day Coverage in Time Block Plan**
    - **Validates: Requirements 6.1, 6.3, 6.4**
  
  - [ ] 7.5 Write property tests for time allocation and upcoming tasks
    - **Property 17: Time Allocation Conservation**
    - **Property 18: Next Week Assignments in HEADS UP**
    - **Validates: Requirements 6.5, 6.6**
  
  - [ ] 7.6 Write property test for output format structure
    - **Property 20: Output Format Structure Consistency**
    - **Validates: Requirements 7.3, 12.5, 13.1**
  
  - [ ]* 7.7 Create hypothesis strategies for test data generation
    - Create date strategy relative to today
    - Create course code strategy
    - Create assignment name strategy with special characters
    - Create estimated_hours strategy (valid and invalid)
    - Create status strategy with edge cases
    - Create notes strategy (empty, whitespace, content)

- [ ] 8. Create workshop presentation slides
  - [ ] 8.1 Create introduction slides
    - Workshop overview and objectives
    - Prerequisites and setup requirements
    - Two-stage progression explanation
    - _Requirements: 10.2_
  
  - [ ] 8.2 Create agent concepts slides
    - What are AI agents
    - Strands SDK architecture overview
    - Tools and tool orchestration
    - _Requirements: 10.2_
  
  - [ ] 8.3 Create AWS integration slides
    - AWS Bedrock overview
    - Claude Sonnet 4.5 capabilities
    - Agent Core Service architecture
    - _Requirements: 10.2_
  
  - [ ] 8.4 Create hands-on exercise slides
    - Stage One walkthrough
    - Stage Two walkthrough
    - Testing and validation
    - _Requirements: 10.2_

- [ ] 9. Create solution code for both stages
  - [ ] 9.1 Create stage_one_solution.py
    - Implement basic agent with web_search tool
    - Include AWS credentials validation
    - Include system prompt loading
    - Add comments explaining each component
    - _Requirements: 10.3_
  
  - [ ] 9.2 Create stage_two_solution.py
    - Implement complete agent with load_assignments tool
    - Include all error handling and validation
    - Include priority score calculation
    - Include comprehensive comments
    - _Requirements: 10.3, 7.6_
  
  - [ ]* 9.3 Write integration tests for solution code
    - Test stage_one_solution runs without errors
    - Test stage_two_solution with all example CSVs
    - Verify outputs match expected format
    - _Requirements: 12.2, 12.5_

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Create AWS infrastructure templates
  - [ ] 11.1 Create CloudFormation template for Agent Core Service
    - Define Lambda function or ECS container for agent hosting
    - Configure IAM role with Bedrock and CloudWatch permissions
    - Set up CloudWatch log group
    - Configure API Gateway for HTTP invocation
    - Add resource tagging for workshop identification
    - _Requirements: 8.2, 8.3, 14.1, 14.2, 14.5_
  
  - [ ] 11.2 Create Terraform alternative template
    - Implement same infrastructure as CloudFormation
    - Use Terraform AWS provider
    - Include outputs for API endpoint and log group
    - _Requirements: 14.1, 14.2_
  
  - [ ] 11.3 Add IAM policy definitions
    - Create policy for bedrock:InvokeModel permission
    - Create policy for logs:CreateLogStream and logs:PutLogEvents
    - Attach policies to Agent Core Service role
    - _Requirements: 14.2_
  
  - [ ] 11.4 Document infrastructure deployment process
    - Add CloudFormation deployment commands to guide
    - Add Terraform deployment commands to guide
    - Document how to retrieve API endpoint from outputs
    - Add infrastructure teardown instructions
    - _Requirements: 14.3, 14.6_
  
  - [ ]* 11.5 Write integration tests for infrastructure deployment
    - Test CloudFormation stack creation
    - Test deployed agent invocation via HTTP
    - Test CloudWatch logs capture
    - Test infrastructure teardown
    - _Requirements: 8.5, Integration Testing_
  
  - [ ]* 11.6 Validate infrastructure templates
    - Run cfn-lint on CloudFormation template
    - Run terraform validate on Terraform template
    - Verify security configurations
    - _Requirements: 14.4_

- [ ] 12. Create validation and testing utilities
  - [ ] 12.1 Create CSV validation script
    - Check for required columns
    - Validate date formats
    - Validate estimated_hours are numeric
    - Report specific validation errors
    - _Requirements: 12.4_
  
  - [ ] 12.2 Create expected output files for test CSVs
    - Generate expected Daily Briefing for current_week_assignments.csv
    - Generate expected Daily Briefing for overdue_assignments.csv
    - Generate expected Daily Briefing for mixed_assignments.csv
    - _Requirements: 12.2_
  
  - [ ] 12.3 Add testing section to workshop guide
    - Document how to run validation script
    - Provide steps to verify agent behavior
    - Include comparison with expected outputs
    - _Requirements: 12.3_
  
  - [ ]* 12.4 Write unit tests for validation script
    - Test validation with valid CSVs
    - Test validation with invalid CSVs
    - Verify error reporting accuracy

- [ ] 13. Update requirements.txt with all dependencies
  - [ ] 13.1 Add testing dependencies
    - Add pytest
    - Add hypothesis for property-based testing
    - Add pytest-cov for coverage reporting
    - _Requirements: 2.4_
  
  - [ ] 13.2 Add AWS and infrastructure dependencies
    - Add boto3 for AWS SDK
    - Add botocore for AWS error handling
    - Verify strands-agents and strands-agents-tools versions
    - _Requirements: 2.4_
  
  - [ ] 13.3 Add development and validation dependencies
    - Add flake8 for linting
    - Add mypy for type checking
    - Add requests for HTTP testing

- [ ] 14. Create project structure and organize files
  - [ ] 14.1 Create directory structure
    - Create examples/ directory for CSV files
    - Create solutions/ directory for solution code
    - Create prompts/ directory for system prompt variants
    - Create infrastructure/ directory for IaC templates
    - Create tests/ directory for test suite
    - Create slides/ directory for presentation materials
  
  - [ ] 14.2 Move and organize existing files
    - Keep agent.py, guide.md, system_prompt.txt, requirements.txt in root
    - Move example CSVs to examples/
    - Move solution code to solutions/
    - Move alternative prompts to prompts/
    - Move IaC templates to infrastructure/
  
  - [ ] 14.3 Create README.md for project overview
    - Add project description
    - Add quick start instructions
    - Add directory structure explanation
    - Add links to workshop guide
    - _Requirements: 10.1_

- [ ] 15. Final integration and validation
  - [ ] 15.1 Run complete test suite
    - Execute all property-based tests
    - Execute all unit tests
    - Execute all integration tests (with AWS credentials)
    - Generate coverage report
  
  - [ ] 15.2 Validate workshop materials completeness
    - Verify all required files exist
    - Check guide completeness
    - Verify example CSVs and expected outputs
    - Verify solution code runs successfully
    - _Requirements: 10.1, 10.2, 10.3, 10.5_
  
  - [ ] 15.3 Test end-to-end workshop flow
    - Follow Stage One exercise from guide
    - Follow Stage Two exercise from guide
    - Test with all example CSVs
    - Verify deployment process
    - _Requirements: 1.1, 1.4, 8.1_
  
  - [ ]* 15.4 Create CI/CD pipeline configuration
    - Create GitHub Actions or similar workflow
    - Add linting step
    - Add unit and property test step
    - Add integration test step (conditional)
    - Add documentation validation step

- [ ] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property-based tests validate universal correctness properties from the design document
- Integration tests require AWS credentials and may incur costs
- The workshop system is designed for 2-3 hour workshop duration
- Infrastructure templates include teardown instructions to avoid ongoing AWS costs
