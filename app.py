import streamlit as st
import pandas as pd
import json
import re
import os
from openai import OpenAI
from dotenv import load_dotenv

# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(page_title="Execution Intelligence Agent", layout="wide")

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

st.title("🚀 Execution Intelligence Agent")

# -------------------------------
# SESSION STATE
# -------------------------------
if "last_input" not in st.session_state:
    st.session_state.last_input = None

if "cached_tasks" not in st.session_state:
    st.session_state.cached_tasks = None

# -------------------------------
# TEAM DATA
# -------------------------------
data = {
    "Employee": ["John", "Mary", "Alex"],
    "CurrentTasks": [2, 4, 1],
    "Capacity": [5, 5, 5],
    "Skill": ["Data", "Frontend", "Backend"]
}
df = pd.DataFrame(data)

# -------------------------------
# HELPERS
# -------------------------------
def is_vague_input(text):
    return len(text.split()) <= 2


def normalize_effort(effort):
    e = str(effort).lower()
    if "low" in e:
        return "Low"
    if "high" in e:
        return "High"
    return "Medium"


def correct_skill(task, skill):
    t = task.lower()
    if any(x in t for x in ["ui", "layout", "menu", "filter", "dashboard"]):
        return "Frontend"
    if any(x in t for x in ["data", "metrics"]):
        return "Data"
    return skill


def assign_task(skill, df):
    df_copy = df.copy()
    df_copy["Available"] = df_copy["Capacity"] - df_copy["CurrentTasks"]

    df_copy["Score"] = 0
    df_copy.loc[df_copy["Skill"] == skill, "Score"] += 5
    df_copy["Score"] += df_copy["Available"]

    best = df_copy.sort_values(by="Score", ascending=False).iloc[0]
    return best["Employee"], best["Available"], "Best fit (skill + availability)"


def split_tasks(main_tasks):
    all_subtasks = []

    for task in main_tasks:
        try:
            prompt = f"""
            You are an AI Project Manager.

            Break the task into smaller implementation tasks.

            STRICT RULES:
            - Maximum 2 subtasks
            - Use action verbs: Create, Build, Implement, Develop
            - Do NOT use: Design, Plan, Define, Analyze, Document
            - Keep tasks simple and executable
            - Effort must be ONLY: Low, Medium, High

            Task: {task['task']}

            Respond ONLY in JSON array with:
            - task
            - skill
            - priority
            - effort
            """

            res = client.chat.completions.create(
                model="meta-llama/llama-3-8b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            raw = res.choices[0].message.content
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            subs = json.loads(match.group()) if match else []

            all_subtasks.extend(subs)

        except:
            continue

    return all_subtasks[:3]


def add_dependencies(tasks):
    for i in range(len(tasks)):
        tasks[i]["depends_on"] = None if i == 0 else tasks[i-1]["task"]
    return tasks


def filter_bad_tasks(tasks):
    banned = [
        "login", "signup", "authentication",
        "shutdown", "operating system",
        "gather", "document", "define", "analyze",
        "requirement", "stakeholder", "discussion",
        "design", "plan"
    ]

    clean = []
    for t in tasks:
        text = t.get("task", "").lower()
        if not any(word in text for word in banned):
            clean.append(t)

    return clean[:3]


# -------------------------------
# PROMPTS
# -------------------------------
MAIN_PROMPT = """
You are an AI Project Manager.

Break down the instruction into EXACTLY 3 implementation tasks.

STRICT RULES:
- Use action verbs: Create, Build, Implement, Develop
- Do NOT use: Design, Plan, Define, Analyze, Document
- Tasks must be practical and executable
- Do NOT assume domain unless specified
- Avoid abstract tasks
- Effort must be ONLY: Low, Medium, High

Respond ONLY in JSON array with:
- task
- skill
- priority
- effort
"""

VAGUE_PROMPT = """
You are an AI Project Manager.

User input is vague.

Generate EXACTLY 3 simple implementation tasks.

STRICT RULES:
- Use action verbs: Create, Build, Implement, Develop
- Do NOT use: Design, Plan, Define, Analyze
- Tasks must be simple and executable
- Effort must be ONLY: Low, Medium, High

Respond ONLY in JSON array with:
- task
- skill
- priority
- effort
"""

# -------------------------------
# UI
# -------------------------------
col1, col2 = st.columns(2)

with col1:
    user_input = st.text_area("Enter instruction")

    if user_input.count("\n") >= 2:
        st.warning("Please enter a single instruction for better results.")
        st.stop()

    colA, colB = st.columns(2)
    with colA:
        run = st.button("Analyze")
    with colB:
        if st.button("Reset"):
            st.session_state.last_input = None
            st.session_state.cached_tasks = None

    st.dataframe(df)

with col2:
    st.header("📊 Execution Plan")

    if run:

        if user_input == st.session_state.last_input:
            tasks = st.session_state.cached_tasks
        else:
            is_vague = is_vague_input(user_input)
            prompt = VAGUE_PROMPT if is_vague else MAIN_PROMPT

            res = client.chat.completions.create(
                model="meta-llama/llama-3-8b-instruct",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0
            )

            raw = res.choices[0].message.content
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            tasks = json.loads(match.group()) if match else []

            tasks = tasks[:3]

            st.session_state.last_input = user_input
            st.session_state.cached_tasks = tasks

        tasks = filter_bad_tasks(tasks)

        if not tasks:
            st.error("No valid tasks generated")
            st.stop()

        is_vague = is_vague_input(user_input)

        if not is_vague and len(tasks) > 2:
            subtasks = split_tasks(tasks)
        else:
            subtasks = tasks

        subtasks = add_dependencies(subtasks)

        for t in subtasks:
            t["effort"] = normalize_effort(t.get("effort"))

        st.success("AI Analysis Complete")

        temp_df = df.copy()

        for t in subtasks:

            skill = correct_skill(t.get("task", ""), t.get("skill", "Frontend"))
            emp, avail, reason = assign_task(skill, temp_df)

            st.markdown(f"### 🔹 {t.get('task')}")

            if avail < 0:
                st.write(f"Overloaded (+{abs(avail)})")
            else:
                st.write(f"Available Capacity: {avail}")

            st.write(f"Assigned to: {emp}")
            st.write(f"Priority: {t.get('priority')}")
            st.write(f"Effort: {t.get('effort')}")
            st.write(f"Depends on: {t.get('depends_on')}")
            st.write(reason)

            st.markdown("---")

            temp_df.loc[temp_df["Employee"] == emp, "CurrentTasks"] += 1

        st.success(f"{len(subtasks)} tasks processed")