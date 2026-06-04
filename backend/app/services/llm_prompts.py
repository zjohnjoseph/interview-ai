RESUME_ANALYSIS_PROMPT = """\
You are an expert technical recruiter analyzing a candidate's resume.

Extract structured information from the following resume text.

Resume:
{resume_text}

Analyze the resume and return a JSON object with exactly these fields:
- technical_skills: array of strings — all technical skills mentioned
  (languages, frameworks, tools, databases, etc.)
- experience_years: integer — total years of professional software experience
  (0 if none found)
- seniority_assessment: string — one of exactly: "junior", "mid", or "senior"
  - junior: 0-2 years or limited scope of work
  - mid: 2-5 years with independent project ownership
  - senior: 5+ years with leadership, architecture, or mentoring
- primary_languages: array of strings — top 1-3 programming languages by prominence
- strengths: array of strings — 2-4 areas where the candidate demonstrates clear depth
- potential_gaps: array of strings — 2-4 areas likely underrepresented given the role
- experience_summary: string — one paragraph summarizing the candidate's background
  (2-3 sentences)

Return ONLY valid JSON. No markdown fences, no code blocks, no preamble, \
no text outside the JSON object.\
"""

QUESTION_GENERATION_PROMPT = """\
You are a senior technical interviewer designing interview questions.

Job context:
- Job description: {job_description}
- Required skills: {required_skills}
- Seniority level: {role_level}

Candidate profile:
{candidate_profile}

Questions already asked in this interview (do not repeat these topics):
{interview_history}

Similar questions from the question corpus (prefer these if highly relevant \
— include the corpus_question_id):
{similar_questions}

Generate ONE interview question appropriate for the candidate's level and the job \
requirements. Cover a topic not yet addressed. If a corpus question is a strong fit, \
adapt or use it directly and set corpus_question_id to its UUID. Otherwise generate a \
fresh question and set corpus_question_id to null.

Return a JSON object with exactly these fields:
- question_text: string — the full interview question to ask the candidate
- domain: string — one of exactly:
  "python", "data_structures", "sql", "system_design", "ml", "apis"
- difficulty: string — one of exactly: "easy", "medium", "hard"
  (calibrated to the seniority level)
- reference_answer: string — a complete model answer that a strong candidate would give
- corpus_question_id: string or null — UUID of the corpus question used, or null if new
- reasoning: string — one sentence explaining why this question is the right choice now

Return ONLY valid JSON. No markdown fences, no code blocks, no preamble, \
no text outside the JSON object.\
"""

ANSWER_EVALUATION_PROMPT = """\
You are an expert technical interviewer evaluating a candidate's answer.

Interview context:
- Job description: {job_description}
- Seniority level: {role_level}

Question asked:
{question_text}

Reference answer (what a strong candidate should cover):
{reference_answer}

Candidate's answer:
{candidate_answer}

Score the candidate's answer on four dimensions, each from 0.0 to 10.0:
- accuracy: How factually correct and technically sound is the answer?
- completeness: How thoroughly does it cover the key concepts in the reference answer?
- clarity: How clearly and concisely is the answer communicated?
- score: Overall score weighting all three dimensions equally.

Calibrate scores relative to the seniority level ({role_level}):
- A junior candidate giving a basic but correct answer should score 7.0+.
- A senior candidate giving that same basic answer should score 4.0-5.0
  (more depth expected).

Score rubric:
- 9.0-10.0: Exceptional — exceeds expectations, adds insight beyond the reference
- 7.0-8.9: Strong — meets expectations for the level, covers all key concepts
- 5.0-6.9: Adequate — partially correct, missing some key concepts
- 3.0-4.9: Below expectations — significant gaps or misconceptions
- 0.0-2.9: Incorrect or irrelevant

Return a JSON object with exactly these fields:
- score: float (0.0-10.0) — overall score
- accuracy: float (0.0-10.0)
- completeness: float (0.0-10.0)
- clarity: float (0.0-10.0)
- feedback: string — 2-4 sentences of specific, constructive feedback explaining
  the scores, what was done well, and what was missing

Return ONLY valid JSON. No markdown fences, no code blocks, no preamble, \
no text outside the JSON object.\
"""

FOLLOW_UP_DECISION_PROMPT = """\
You are a technical interviewer deciding whether to probe deeper or move on.

Seniority level: {role_level}

Question that was asked:
{question_text}

Candidate's answer:
{candidate_answer}

Evaluation results:
{evaluation}

Decide whether to ask a follow-up question or move on to a new topic.

Ask a follow-up when:
- The overall score is below 6.0, OR
- The accuracy score is below 5.0, OR
- The candidate showed partial understanding worth exploring further

Move on when:
- The overall score is 6.0 or above AND accuracy is 5.0 or above, AND
- The answer was sufficiently complete for the seniority level

If asking a follow-up, generate a targeted question that probes the specific weakness \
identified in the evaluation. The follow-up should be more specific than the original.

Return a JSON object with exactly these fields:
- needs_follow_up: boolean — true if a follow-up is warranted
- follow_up_question: string or null — the follow-up question if needs_follow_up is true,
  otherwise null
- reasoning: string — one sentence explaining the decision

Return ONLY valid JSON. No markdown fences, no code blocks, no preamble, \
no text outside the JSON object.\
"""
