import streamlit as st
import pandas as pd
import json
import re
import os
from datetime import datetime
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


def extract_deadline_days(text):
    text = text.lower()

    if "today" in text or "tomorrow" in text:
        return 1
    if "week" in text:
        return 7
    if "month" in text:
        return 30
    if "monday" in text:
        return 2

    match = re.search(r"(\d+)\s*day", text)
    if match:
        return int(match.group(1))

    return None


def effort_to_hours(effort):
    return {"Low": 2, "Medium": 4, "High": 8}.get(effort, 4)


def correct_skill(task, skill):
    t = task.lower()

    if any(x in t for x in ["ui", "layout", "dashboard", "menu"]):
        return "Frontend"
    if any(x in t for x in ["data", "metrics", "schema"]):
        return "Data"

    return skill


# 🔥 ASSIGNMENT
def assign_task(skill, df):
    df_copy = df.copy()
    df_copy["Available"] = df_copy["Capacity"] - df_copy["CurrentTasks"]

    df_copy["Score"] = 0
    df_copy.loc[df_copy["Skill"] == skill, "Score"] += 5
    df_copy["Score"] += df_copy["Available"]

    best = df_copy.sort_values(by="Score", ascending=False).iloc[0]

    return best["Employee"], best["Available"], "Best fit (skill + availability)"


# 🔥 SPLIT TASKS (STEP 1)
def split_tasks(main_tasks):
    all_subtasks = []

    for task in main_tasks:
        try:
            prompt = f"""
            You are continuing an execution planning task.

            DO NOT change domain.
            Keep tasks simple and within scope.

            Break this task into MAXIMUM 2 subtasks.

            Task: {task['task']}

            Each subtask must include:
            - task
            - skill
            - priority
            - effort (Low / Medium / High)

            Respond ONLY in JSON array.
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


# 🔥 DEPENDENCIES
def add_dependencies(tasks):
    for i in range(len(tasks)):
        tasks[i]["depends_on"] = None if i == 0 else tasks[i-1]["task"]
    return tasks


# -------------------------------
# PROMPTS
# -------------------------------
MAIN_PROMPT = """
Generate EXACTLY 3 execution tasks.

Include:
- task
- skill
- priority
- effort (Low / Medium / High)

Stay within task/workload system.
No ecommerce/sales assumptions.

JSON only.
"""

VAGUE_PROMPT = """
Generate EXACTLY 3 simple UI tasks.

No backend, no DB.

Include:
- task
- skill (Frontend)
- priority (Medium)
- effort (Low)

JSON only.
"""

# -------------------------------
# UI
# -------------------------------
col1, col2 = st.columns(2)

with col1:
    st.header("📝 Input")
    user_input = st.text_area("Enter instruction")
    run = st.button("Analyze")

    st.subheader("👥 Team Status")
    st.dataframe(df)

    # 🔥 WORKLOAD DASHBOARD
    st.subheader("📊 Workload Distribution")

    chart_df = df.copy()
    chart_df["Used"] = chart_df["CurrentTasks"]

    st.bar_chart(chart_df.set_index("Employee")[["Used", "Capacity"]])

# -------------------------------
# OUTPUT
# -------------------------------
with col2:
    st.header("📊 Execution Plan")

    if run:

        is_vague = is_vague_input(user_input)
        deadline_days = extract_deadline_days(user_input)

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

        if not tasks:
            st.error("No tasks generated")
            st.stop()

        # 🔥 STEP 2 (subtasks logic)
        if not is_vague and len(tasks) > 2:
            subtasks = split_tasks(tasks)
        else:
            subtasks = tasks

        # 🔥 STEP 3 (dependencies)
        subtasks = add_dependencies(subtasks)

        st.success("✅ AI Analysis Complete")

        # 🔥 FEASIBILITY
        total_hours = sum(effort_to_hours(t.get("effort", "Medium")) for t in subtasks)
        team_hours = sum((row["Capacity"] - row["CurrentTasks"]) * 4 for _, row in df.iterrows())

        if deadline_days:
            max_hours = team_hours * deadline_days
            if total_hours > max_hours:
                st.error(f"❌ Not feasible ({total_hours}h needed vs {max_hours}h available)")
            else:
                st.success(f"✅ Feasible ({total_hours}h vs {max_hours}h)")
        else:
            st.info(f"ℹ️ Estimated effort: {total_hours}h")

        temp_df = df.copy()

        # 🔥 STEP 4 (loop on subtasks)
        for t in subtasks:

            skill = correct_skill(t.get("task", ""), t.get("skill", "Frontend"))
            emp, avail, reason = assign_task(skill, temp_df)

            st.markdown(f"### 🔹 {t.get('task')}")

            if avail < 0:
                st.write(f"📊 Capacity Status: Overloaded (+{abs(avail)})")
            else:
                st.write(f"📊 Available Capacity: {avail}")

            st.write(f"👤 Assigned to: {emp}")
            st.write(f"🔥 Priority: {t.get('priority')}")
            st.write(f"⏱ Effort: {t.get('effort')}")
            st.write(f"🔗 Depends on: {t.get('depends_on')}")
            st.write(f"🧠 {reason}")

            st.markdown("---")

            temp_df.loc[temp_df["Employee"] == emp, "CurrentTasks"] += 1

        st.success(f"✅ {len(subtasks)} tasks processed")