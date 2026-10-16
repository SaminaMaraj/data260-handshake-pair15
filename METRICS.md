## Reliability notes

The assistant completed a separate 20-turn reliability run.

| Metric | Result |
|---|---:|
| Total turns | 20 |
| Completed turns | 20 |
| Iteration-limit failures | 0 |
| Total tool calls | 18 |

The run included job searches, event searches, preference-based searches, follow-up questions, and no-match requests. The assistant completed all 20 turns without reaching the safe iteration limit.

Several incorrect tool arguments were detected during development and corrected:

- Incorrect student ID
- Incorrect city and salary preference
- Invalid job category
- Incorrect event date

The assistant returned no-match responses instead of inventing database records.