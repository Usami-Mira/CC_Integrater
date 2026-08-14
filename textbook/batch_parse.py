"""
MinerU 在线 API 批量解析脚本
用法: python mineru_batch_parse.py --token YOUR_TOKEN --pdf D:\path\to\book.pdf --output D:\temp\mineru_output
"""

import argparse
import os
import time
import zipfile
import requests
from pathlib import Path

# ============ 配置区 ============
BASE_URL = "https://mineru.net/api/v4"
MAX_PAGES_PER_FILE = 200       # MinerU 单文件页数上限
MODEL_VERSION = "vlm"          # 推荐 vlm，公式识别精度最高
LANGUAGE = "ch"                # 中英文混合教材
ENABLE_FORMULA = True          # 物理教材必开
POLL_INTERVAL = 15             # 轮询间隔(秒)
# ================================


def split_pdf(pdf_path: str, output_dir: str, max_pages: int = MAX_PAGES_PER_FILE):
    """按页数拆分 PDF，返回拆分后的文件路径列表"""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    parts = []

    for i in range(0, total, max_pages):
        end = min(i + max_pages, total)
        writer = PdfWriter()
        for p in range(i, end):
            writer.add_page(reader.pages[p])

        part_path = os.path.join(output_dir, f"part_{i // max_pages + 1}.pdf")
        with open(part_path, "wb") as f:
            writer.write(f)
        parts.append(part_path)
        print(f"  ✅ 已拆分: {part_path} (第 {i + 1}-{end} 页)")

    return parts


def upload_and_submit(token: str, file_paths: list[str]):
    """批量申请上传链接 → PUT 上传 → 自动提交解析任务，返回 batch_id"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    files_payload = [
        {"name": os.path.basename(p), "data_id": Path(p).stem}
        for p in file_paths
    ]

    print(f"\n📤 申请上传链接 ({len(file_paths)} 个文件)...")
    resp = requests.post(f"{BASE_URL}/file-urls/batch", headers=headers, json={
        "files": files_payload,
        "model_version": MODEL_VERSION,
        "enable_formula": ENABLE_FORMULA,
        "language": LANGUAGE,
    })
    result = resp.json()

    if result["code"] != 0:
        raise RuntimeError(f"申请上传链接失败: {result['msg']}")

    batch_id = result["data"]["batch_id"]
    urls = result["data"]["file_urls"]
    print(f"  ✅ batch_id: {batch_id}")

    for url, path in zip(urls, file_paths):
        print(f"  ⬆️  上传中: {os.path.basename(path)} ...", end=" ")
        with open(path, "rb") as f:
            r = requests.put(url, data=f)
        if r.status_code == 200:
            print("✅")
        else:
            print(f"❌ HTTP {r.status_code}")
            raise RuntimeError(f"上传失败: {path}")

    return batch_id


def poll_and_download(token: str, batch_id: str, output_dir: str):
    """轮询批量任务状态，完成后自动下载并解压 zip"""
    headers = {"Authorization": f"Bearer {token}"}
    print(f"\n⏳ 开始轮询解析进度 (每 {POLL_INTERVAL}s)...")

    while True:
        resp = requests.get(
            f"{BASE_URL}/extract-results/batch/{batch_id}", headers=headers
        )
        results = resp.json()["data"]["extract_result"]

        all_done = True
        for r in results:
            name = r["file_name"]
            state = r["state"]

            if state == "done":
                zip_url = r["full_zip_url"]
                zip_path = os.path.join(output_dir, f"{Path(name).stem}.zip")

                if not os.path.exists(zip_path):
                    print(f"  📥 下载完成: {name}")
                    with requests.get(zip_url, stream=True) as zr:
                        with open(zip_path, "wb") as zf:
                            for chunk in zr.iter_content(chunk_size=8192):
                                zf.write(chunk)

                    # 自动解压到同名文件夹
                    extract_dir = os.path.join(output_dir, Path(name).stem)
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(extract_dir)
                    print(f"  📂 已解压到: {extract_dir}")
            elif state == "failed":
                print(f"  ❌ {name}: {r.get('err_msg', '未知错误')}")
            else:
                progress = r.get("extract_progress", {})
                extracted = progress.get("extracted_pages", "?")
                total = progress.get("total_pages", "?")
                print(f"  ⏳ {name}: {state} ({extracted}/{total})")
                all_done = False

        if all_done:
            print("\n🎉 全部解析完成！")
            break

        time.sleep(POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description="MinerU 在线 API 批量解析")
    parser.add_argument("--token", required=True, help="MinerU API Token")
    parser.add_argument("--pdf", required=True, help="PDF 文件路径")
    parser.add_argument("--output", default="./mineru_output", help="输出目录")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    split_dir = os.path.join(args.output, "_split")
    os.makedirs(split_dir, exist_ok=True)

    # Step 1: 拆分
    print(f"📖 拆分 PDF: {args.pdf}")
    parts = split_pdf(args.pdf, split_dir)

    # Step 2: 上传并提交
    batch_id = upload_and_submit(args.token, parts)

    # Step 3: 轮询 & 下载
    poll_and_download(args.token, batch_id, args.output)

    print(f"\n📁 所有结果保存在: {args.output}")
    print("💡 每个分卷的 full.md 即为最终 Markdown，可直接导入知识库")


if __name__ == "__main__":
    main()