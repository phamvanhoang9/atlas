import asyncio
import sys
import os
import json
from dotenv import load_dotenv

os.environ["ENABLE_EVALUATION"] = "true"
os.environ["EVALUATION_MODE"] = "online"
os.environ["EVAL_LLM_PROVIDER"] = "openai"
os.environ["EVAL_LLM_MODEL"] = "gpt-4o-mini"
os.environ["EVAL_TOP_K"] = "3"

from src.orchestration.runner import LangGraphResearcher

async def run():
    sys.stdout.reconfigure(encoding='utf-8')
    load_dotenv()
    
    query = "Hãy giải thích sự khác biệt giữa RLHF và DPO trong việc fine-tune LLM."
    print(f"Bắt đầu chạy Online Pipeline cho query:\n'{query}'\n")
    
    researcher = LangGraphResearcher(
        query=query,
        report_type="phân tích",
        config_path="config.json"
    )
    
    final_state = await researcher.run_with_state()
    
    print("\n--- KẾT QUẢ SINH BÁO CÁO ---")
    report = final_state.get("report", "")
    print(report[:500] + "...\n[Báo cáo đã bị cắt bớt để dễ nhìn]")
    
    print("\n--- KẾT QUẢ ĐÁNH GIÁ (ONLINE EVALUATION) ---")
    eval_res = final_state.get("evaluation_result")
    if eval_res:
        print(f"Overall Score: {eval_res.get('overall_score')}")
        print(f"Status: {eval_res.get('label').upper()}")
        print("\nCác chỉ số:")
        metrics = eval_res.get("metrics", {})
        for k, v in metrics.items():
            print(f"- {k}: {v.get('score')} ({v.get('label')})")
    else:
        print("Không tìm thấy kết quả evaluation trong final_state.")

if __name__ == "__main__":
    asyncio.run(run())
