# AI_USE.md

## AI assistant use

During Lab 1 development, AI assistance was used for debugging, code organization, API design, test planning, and documentation review.

The final implementation was tested locally using FastAPI, MySQL, Ollama, and the Qwen3 model.

## Incorrect output 1: wrong student ID

During the first assistant test, the model attempted to call:

~~~text
get_student_preferences {"student_id": 123}
~~~

The test request supplied student ID `1`. The model-generated ID was incorrect.

### Detection

The tool-call log was compared with the `student_id=1` argument passed to `run_assistant()`.

### Fix

The loop was changed to force the application-supplied ID:

~~~python
arguments["student_id"] = student_id
~~~

The assistant then correctly used student ID `1`.

## Incorrect output 2: wrong preference values

During the first preference-based job search, the assistant returned Cupertino jobs even though the saved preference was Sunnyvale. It also used a $60,000 salary threshold even though the saved minimum salary was $70,000.

### Detection

The assistant response was compared with the result returned by `get_student_preferences`.

### Fix

The loop now copies the database preference values into the next job-search arguments:

- City
- Category
- Minimum salary
- Preferred skill

The corrected result used Sunnyvale internships with salaries of at least $70,000.

## Incorrect output 3: invalid job category

During the remote data-science test, the model initially attempted to use:

~~~text
category: data science
~~~

The database only accepts these job categories:

~~~text
full_time
part_time
on_campus
internship
~~~

### Detection

The generated category was compared with the allowed database enum values.

### Fix

The assistant loop normalizes a remote data-science request to:

~~~text
category: internship
remote_only: true
skill: Machine Learning
~~~

## Incorrect output 4: incorrect event date

During the computer-science event test, the model initially generated a date in 2023 even though the project date was October 2026.

### Detection

The generated date was compared with the current project date and the requested phrase “next month.”

### Fix

The assistant loop now calculates the first day of the next month programmatically and uses it as the event-search date.

## Verification

After these fixes, the five required assistant tests were run:

1. Internship in the student’s city
2. Remote data-science internship
3. Computer-science event next month
4. Higher-paying follow-up using conversation history
5. Missing company/category with a no-match response

The corrected tests completed without inventing database records.