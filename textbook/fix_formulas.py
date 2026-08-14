#!/usr/bin/env python3
"""
Textbook OCR Formula Correction Pipeline

Usage:
  1. Edit MODEL_CONFIG below with your LLM API endpoint and key
  2. Run: python3 fix_formulas.py [--mode preview|fix] [--input_dir ./em_output/part_1]
     - preview: 只输出需要修复的公式列表，不修改文件
     - fix:     实际修复并写回 markdown 文件（会先备份）

依赖: requests, Pillow (用于读取图片)
"""

import os
import re
import json
import shutil
import base64
import argparse
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# ============================================================================
# MODEL CONFIGURATION — 修改这里接入你自己的模型
# ============================================================================
MODEL_CONFIG = {
    # OpenAI-compatible API 格式
    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "REMOVED_API_KEY",
    "model": "qwen3.6-flash",
    "timeout": 120,
    "max_retries": 3,
}

# 图片目录（相对于 markdown 文件所在目录）
IMAGE_DIR = "images"

# 输出目录
OUTPUT_DIR = "fix_output"

# 并发数（同时发多少个 LLM 请求）
CONCURRENCY = 10

# ============================================================================
# 数据结构
# ============================================================================
@dataclass
class FormulaBlock:
    """一个公式块"""
    file_path: str           # markdown 文件路径
    line_start: int          # 起始行号（1-based）
    line_end: int            # 结束行号
    raw_text: str            # 原始 LaTeX（不含 $$）
    context_before: str      # 公式前的上下文
    context_after: str       # 公式后的上下文
    related_image: Optional[str] = None  # 关联的图片路径（如果有）
    rule_fixed: Optional[str] = None     # 规则修复后的文本（如果有修改）
    llm_fixed: Optional[str] = None      # LLM 修复后的文本
    needs_llm: bool = False  # 是否需要 LLM 进一步处理


# ============================================================================
# 规则修复（Rule-based fixes）
# ============================================================================

def rule_fix_spaces_in_numbers(latex: str) -> str:
    """修复数字中间多余空格: 1. 6 0 2 1 7 6 4 6 2 → 1.602176462"""
    # Pattern: digit space digit, repeated
    # Only fix within number-like contexts (digits, decimal points, parentheses)
    def fix_number_group(m):
        s = m.group(0)
        # Check if it's mostly digits/spaces/decimal/parens
        cleaned = re.sub(r'[\s]', '', s)
        if re.match(r'^[\d.(),]+$', cleaned):
            return cleaned
        return s
    # Match sequences that look like spaced-out numbers
    return re.sub(r'\d(?:\s+[\d.()])+', fix_number_group, latex)


def rule_fix_latex_spacing(latex: str) -> str:
    """修复 LaTeX 命令和参数之间的多余空格"""
    # \frac {a} → \frac{a}
    latex = re.sub(r'(\\[a-zA-Z]+)\s+\{', r'\1{', latex)
    # \frac{a} {b} → \frac{a}{b}
    latex = re.sub(r'\}\s+\{', '}{', latex)
    # \hat {r} → \hat{r}
    latex = re.sub(r'(\\hat|\\vec|\\boldsymbol|\\mathbf|\\mathrm|\\text|\\pmb)\s+\{', r'\1{', latex)
    # _ {0} → _{0}
    latex = re.sub(r'([_^])\s+\{', r'\1{', latex)
    # ^ {- 1 9} → ^{-19} (after number fix)
    latex = re.sub(r'\{\s*-\s*', '{-', latex)
    return latex


def rule_fix_common_ocr_errors(latex: str) -> str:
    """修正常见的 OCR 误识别"""
    # 这些需要非常谨慎，只在明显错误的情况下修复
    # 例如: \times 1 0 ^ {- 1 9} 这种模式
    latex = re.sub(r'(\d)\s+(\d)', r'\1\2', latex)  # 数字间空格
    return latex


def apply_rules(latex: str) -> str:
    """应用所有规则修复"""
    result = latex
    result = rule_fix_spaces_in_numbers(result)
    result = rule_fix_latex_spacing(result)
    result = rule_fix_common_ocr_errors(result)
    # 清理首尾空白
    result = result.strip()
    return result


# ============================================================================
# 公式提取
# ============================================================================

def extract_formulas(md_path: str) -> list[FormulaBlock]:
    """从 markdown 文件中提取所有公式块"""
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    formulas = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Block formula: $$ ... $$
        if line == '$$':
            start_line = i
            j = i + 1
            formula_lines = []
            while j < len(lines) and lines[j].strip() != '$$':
                formula_lines.append(lines[j].rstrip())
                j += 1
            end_line = j

            raw_text = '\n'.join(formula_lines)
            context_before = ''.join(lines[max(0, i-5):i]).strip()
            context_after = ''.join(lines[j+1:j+6]).strip()

            # 检查附近是否有图片（可能公式被存成了图片）
            related_image = find_nearby_image(lines, i, os.path.dirname(md_path))

            formulas.append(FormulaBlock(
                file_path=md_path,
                line_start=start_line + 1,
                line_end=end_line + 1,
                raw_text=raw_text,
                context_before=context_before,
                context_after=context_after,
                related_image=related_image,
            ))
            i = j + 1
        else:
            i += 1

    return formulas


def find_nearby_image(lines: list, formula_line: int, base_dir: str) -> Optional[str]:
    """检查公式附近是否有图片（可能是公式的图片版本）"""
    # 检查公式前后 5 行内是否有 ![](...)
    for offset in range(-5, 6):
        idx = formula_line + offset
        if 0 <= idx < len(lines):
            match = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', lines[idx])
            if match:
                img_path = os.path.join(base_dir, match.group(2))
                if os.path.exists(img_path):
                    return img_path
    return None


@dataclass
class InlineFormulaLine:
    """一行中的行内公式"""
    file_path: str           # markdown 文件路径
    line_number: int         # 行号（1-based）
    line_text: str           # 整行文本
    formulas: list           # [(start_pos, end_pos, formula_text), ...]


def extract_inline_formulas(md_path: str, min_length: int = 20) -> list[InlineFormulaLine]:
    """
    从 markdown 文件中提取行内公式（$ ... $），按行分组。

    Args:
        md_path: markdown 文件路径
        min_length: 只保留至少有一个公式长度 >= min_length 的行

    Returns:
        InlineFormulaLine 列表
    """
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    result = []

    for i, line in enumerate(lines):
        # 跳过 $$ 行（多行公式标记）
        if line.strip() == '$$':
            continue

        # 查找行内 $ ... $ 公式（不是 $$）
        formulas = []
        for match in re.finditer(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', line):
            start_pos = match.start()
            end_pos = match.end()
            formula_text = match.group(1)
            formulas.append((start_pos, end_pos, formula_text))

        # 过滤：至少有一个公式长度 >= min_length
        if formulas and any(len(f[2]) >= min_length for f in formulas):
            result.append(InlineFormulaLine(
                file_path=md_path,
                line_number=i + 1,  # 1-based
                line_text=line.rstrip(),
                formulas=formulas,
            ))

    return result


# ============================================================================
# LLM 调用
# ============================================================================

def call_llm(prompt: str, image_path: Optional[str] = None, session: Optional[object] = None) -> str:
    """
    调用 LLM API 修复公式。
    返回修正后的 LaTeX 字符串。

    这里使用 OpenAI-compatible API 格式。
    如果你用其他格式的 API，修改这个函数即可。
    """
    import requests

    # 使用传入的 session 或创建新的（推荐传入以复用连接）
    if session is None:
        session = requests

    headers = {
        "Authorization": f"Bearer {MODEL_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }

    # 构建消息
    content = []

    # 文本部分
    content.append({
        "type": "text",
        "text": prompt,
    })

    # 图片部分（如果有）
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode()

        # 根据图片格式确定 MIME type
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}
        mime = mime_map.get(ext, 'image/jpeg')

        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{img_data}",
            },
        })

    payload = {
        "model": MODEL_CONFIG["model"],
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 1024,
        "enable_thinking": False,  # 关闭思考模式，加速处理
    }

    for attempt in range(MODEL_CONFIG["max_retries"]):
        try:
            resp = session.post(
                f"{MODEL_CONFIG['api_base']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=MODEL_CONFIG["timeout"],
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt == MODEL_CONFIG["max_retries"] - 1:
                print(f"  [LLM Error] {e}")
                return ""
            import time
            time.sleep(2 ** attempt)

    return ""


def build_llm_prompt(formula: FormulaBlock) -> str:
    """构建 LLM 修复公式的 prompt"""
    prompt = f"""你是一个物理教材 OCR 公式修正助手。

以下是一个从物理教材 PDF 扫描得到的 LaTeX 公式，可能存在 OCR 错误。
请根据物理定律和上下文判断并修正错误。

## 公式上下文（前文）
{formula.context_before}

## 当前公式（OCR 结果）
{formula.raw_text}

## 公式上下文（后文）
{formula.context_after}

## 要求
1. 检查公式是否符合物理定律（如库仑定律、牛顿定律等）
2. 检查是否有常见 OCR 错误：
   - 字符误识别（如 r^2 被识别成 3，ε 被识别成 e）
   - 缺少向量标记（如 F 应为 \\boldsymbol{{F}}）
   - 上下标错误
   - 缺失的运算符或括号
3. 如果公式看起来正确，输出原文
4. 只输出修正后的 LaTeX 公式，不要 $$ 包裹，不要任何解释

修正后的公式："""

    return prompt


def batch_fix_inline(lines: list[InlineFormulaLine], session: Optional[object] = None) -> dict[int, str]:
    """
    批量修复行内公式。

    Args:
        lines: InlineFormulaLine 列表（建议 10 个一批）
        session: HTTP session（用于连接复用）

    Returns:
        dict: {line_number: corrected_line_text}
    """
    import requests

    if session is None:
        session = requests

    # System prompt
    system_prompt = """你是一个物理教材 OCR 文档修正助手。

这是一个从物理教材 PDF 经 MinerU OCR 扫描得到的 Markdown 文档。
OCR 过程中可能产生以下类型的错误：

1. 字符误识别（如 r² 被识别成 3，ε 被识别成 e，α 被识别成 a）
2. 粗体/向量标记错误（标量电荷 q 不应加粗，矢量 F 需要 \\boldsymbol{F}）
3. 数字中间多余空格（如 1. 6 0 2 → 1.602）
4. LaTeX 命令和参数之间的空格（如 \\frac {a} → \\frac{a}）
5. 上下标位置或内容错误
6. 缺失的运算符或括号

用户会发送包含行内公式（$ ... $）的文本行。请修正其中的公式错误。

规则：
- 如果公式正确，保持原样
- 只修正 $ ... $ 内的公式，不要改动公式外的文本
- 只输出修正后的整行文本，不要解释，不要 markdown 代码块
- 每行对应一个编号，按编号顺序输出"""

    # Build user message
    user_lines = []
    for i, il in enumerate(lines, 1):
        user_lines.append(f"{i}. {il.line_text}")

    user_message = "请修正以下文本行中的行内公式：\n\n" + "\n".join(user_lines)

    # API call
    headers = {
        "Authorization": f"Bearer {MODEL_CONFIG['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL_CONFIG["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 4096,
        "enable_thinking": False,
    }

    for attempt in range(MODEL_CONFIG["max_retries"]):
        try:
            resp = session.post(
                f"{MODEL_CONFIG['api_base']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=MODEL_CONFIG["timeout"],
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data["choices"][0]["message"]["content"].strip()

            # Parse response: extract numbered lines
            result = {}
            response_lines = response_text.split('\n')
            for resp_line in response_lines:
                resp_line = resp_line.strip()
                if not resp_line:
                    continue

                # Match pattern: "1. corrected text"
                match = re.match(r'^(\d+)\.\s*(.+)$', resp_line)
                if match:
                    idx = int(match.group(1)) - 1  # 0-based
                    corrected = match.group(2)
                    if 0 <= idx < len(lines):
                        result[lines[idx].line_number] = corrected

            return result

        except Exception as e:
            if attempt == MODEL_CONFIG["max_retries"] - 1:
                print(f"  [LLM Error] {e}")
                return {}
            import time
            time.sleep(2 ** attempt)

    return {}


# ============================================================================
# 主流程
# ============================================================================

def process_file(md_path: str, mode: str, concurrency: int = CONCURRENCY, with_images: bool = False) -> list[FormulaBlock]:
    """处理单个 markdown 文件"""
    print(f"\n{'='*60}")
    print(f"Processing: {md_path}")
    print(f"{'='*60}")

    formulas = extract_formulas(md_path)
    print(f"  Found {len(formulas)} formula blocks")

    rule_fixed_count = 0
    needs_llm_count = 0

    for i, f in enumerate(formulas):
        # 1. 规则修复
        fixed = apply_rules(f.raw_text)
        if fixed != f.raw_text:
            f.rule_fixed = fixed
            rule_fixed_count += 1

        # 2. 判断是否需要 LLM（目前策略：所有公式都交给 LLM 检查）
        # 未来可以加启发式规则跳过明显正确的公式
        f.needs_llm = True
        needs_llm_count += 1

    print(f"  Rule-fixed: {rule_fixed_count}")
    print(f"  Needs LLM: {needs_llm_count}")

    # 3. 调用 LLM 修复（并发）
    if mode == 'fix':
        import requests as _requests
        http_session = _requests.Session()  # 复用连接

        llm_formulas = [f for f in formulas if f.needs_llm]
        ok_count = 0
        fail_count = 0

        def fix_one(f):
            text_to_fix = f.rule_fixed if f.rule_fixed else f.raw_text
            img = f.related_image if with_images else None
            prompt = build_llm_prompt(FormulaBlock(
                file_path=f.file_path,
                line_start=f.line_start,
                line_end=f.line_end,
                raw_text=text_to_fix,
                context_before=f.context_before,
                context_after=f.context_after,
                related_image=img,
            ))
            result = call_llm(prompt, img, session=http_session)
            if result:
                f.llm_fixed = result
                return True
            return False

        progress = tqdm(total=len(llm_formulas), desc="LLM fixing", unit="formula") if HAS_TQDM else None

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(fix_one, f): f for f in llm_formulas}
            for future in as_completed(futures):
                success = future.result()
                if success:
                    ok_count += 1
                else:
                    fail_count += 1
                if progress:
                    progress.update(1)
                    progress.set_postfix(ok=ok_count, fail=fail_count)
                else:
                    done = ok_count + fail_count
                    print(f"  [{done}/{len(llm_formulas)}] ok={ok_count} fail={fail_count}")

        if progress:
            progress.close()
        print(f"  LLM done: {ok_count} ok, {fail_count} failed")

    return formulas


def write_back(md_path: str, formulas: list[FormulaBlock], output_dir: str):
    """将修正后的公式写回 markdown 文件（先备份）"""
    # 备份原文件
    backup_path = md_path + '.bak'
    shutil.copy2(md_path, backup_path)

    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    # 按行号倒序替换（避免行号偏移）
    for formula in sorted(formulas, key=lambda x: x.line_start, reverse=True):
        # 选择最终修正结果：LLM > 规则 > 原文
        final_text = formula.llm_fixed or formula.rule_fixed
        if not final_text:
            continue

        # 替换公式内容（line_start 是 $$，line_end 是 $$）
        # 注意：line_start/line_end 是 1-based，需要转为 0-based 索引
        start = formula.line_start - 1  # 1-based → 0-based
        end = formula.line_end          # slice end 是 exclusive，所以不需要 -1
        lines[start:end] = ['$$\n', final_text + '\n', '$$\n']

    # 写入修正后的文件
    fixed_path = os.path.join(output_dir, os.path.basename(md_path))
    os.makedirs(os.path.dirname(fixed_path) or '.', exist_ok=True)
    with open(fixed_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"  Fixed file written to: {fixed_path}")
    print(f"  Original backed up to: {backup_path}")


def process_inline_formulas(md_path: str, output_dir: str, batch_size: int = 10,
                            concurrency: int = CONCURRENCY, min_length: int = 20,
                            log_file: Optional[str] = None):
    """
    处理行内公式：批量调用 LLM 修正。

    Args:
        md_path: markdown 文件路径
        output_dir: 输出目录
        batch_size: 每批处理的行数
        concurrency: 并发数
        min_length: 只处理长度 >= min_length 的公式
        log_file: 日志文件路径（可选）
    """
    import requests as _requests

    print(f"\n{'='*60}")
    print(f"Processing inline formulas: {md_path}")
    print(f"{'='*60}")

    # 提取行内公式
    inline_lines = extract_inline_formulas(md_path, min_length=min_length)
    total_lines = len(inline_lines)
    total_formulas = sum(len(il.formulas) for il in inline_lines)

    print(f"  Lines with formulas (>=20 chars): {total_lines}")
    print(f"  Total formulas: {total_formulas}")
    print(f"  Batch size: {batch_size}, Concurrency: {concurrency}")

    if total_lines == 0:
        print("  No inline formulas to process")
        return

    # 分批
    batches = []
    for i in range(0, total_lines, batch_size):
        batches.append(inline_lines[i:i+batch_size])

    print(f"  Total batches: {len(batches)}")

    # 并发处理
    http_session = _requests.Session()
    corrections = {}  # {line_number: corrected_text}
    ok_count = 0
    fail_count = 0
    missing_lines = []  # 记录未返回的行

    def process_batch(batch):
        result = batch_fix_inline(batch, http_session)
        return result

    progress = tqdm(total=len(batches), desc="Processing batches", unit="batch") if HAS_TQDM else None

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(process_batch, batch): batch for batch in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                result = future.result()
                corrections.update(result)

                # 记录未返回的行
                expected = set(il.line_number for il in batch)
                got = set(result.keys())
                missing = expected - got
                if missing:
                    missing_lines.extend(missing)
                    print(f"  [Warning] Batch missing lines: {sorted(missing)}")

                ok_count += 1
            except Exception as e:
                fail_count += 1
                print(f"  [Error] {e}")

            if progress:
                progress.update(1)
                progress.set_postfix(ok=ok_count, fail=fail_count)

    if progress:
        progress.close()

    print(f"  Batches done: {ok_count} ok, {fail_count} failed")
    print(f"  Lines corrected: {len(corrections)}")

    if missing_lines:
        print(f"  Missing lines: {len(missing_lines)}")
        print(f"    Line numbers: {sorted(missing_lines)}")

    # 写日志
    if log_file:
        import json
        log_data = {
            'file': md_path,
            'total_lines': total_lines,
            'total_formulas': total_formulas,
            'batches': len(batches),
            'lines_corrected': len(corrections),
            'missing_lines': sorted(missing_lines),
            'corrections': {str(k): v for k, v in corrections.items()}
        }
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        print(f"  Log saved to: {log_file}")

    # 写回文件
    with open(md_path, encoding='utf-8') as f:
        lines = f.readlines()

    # 应用修正
    for line_num, corrected in corrections.items():
        idx = line_num - 1  # 1-based → 0-based
        if 0 <= idx < len(lines):
            # 保留原行尾的换行符
            if lines[idx].endswith('\n'):
                lines[idx] = corrected + '\n'
            else:
                lines[idx] = corrected

    # 保存
    output_path = os.path.join(output_dir, os.path.basename(md_path))
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"  Output written to: {output_path}")

    return corrections


def main():
    parser = argparse.ArgumentParser(description='Textbook OCR Formula Correction')
    parser.add_argument('--mode', choices=['preview', 'fix'], default='preview',
                        help='preview: only list formulas; fix: apply corrections')
    parser.add_argument('--input_dir', type=str, default=None,
                        help='Directory containing full.md (e.g. ./em_output/part_1)')
    parser.add_argument('--all', action='store_true',
                        help='Process all parts of all textbooks')
    parser.add_argument('--concurrency', type=int, default=CONCURRENCY,
                        help=f'Max concurrent LLM requests (default: {CONCURRENCY})')
    parser.add_argument('--with-images', action='store_true',
                        help='Send related images to LLM (slower, use for problematic formulas)')
    args = parser.parse_args()

    textbook_dir = os.path.dirname(os.path.abspath(__file__))
    output_base = os.path.join(textbook_dir, OUTPUT_DIR)

    # 确定要处理的文件
    if args.all:
        md_files = sorted([
            os.path.join(dp, f)
            for dp, _, fs in os.walk(textbook_dir)
            for f in fs if f == 'full.md'
        ])
    elif args.input_dir:
        md_files = [os.path.join(args.input_dir, 'full.md')]
    else:
        print("Please specify --input_dir or --all")
        return

    all_formulas = []
    for md_path in md_files:
        if not os.path.exists(md_path):
            print(f"  Skipping (not found): {md_path}")
            continue

        formulas = process_file(md_path, args.mode, args.concurrency, args.with_images)
        all_formulas.extend(formulas)

        if args.mode == 'fix':
            rel_dir = os.path.relpath(os.path.dirname(md_path), textbook_dir)
            output_dir = os.path.join(output_base, rel_dir)
            write_back(md_path, formulas, output_dir)

    # 汇总统计
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total formulas: {len(all_formulas)}")
    print(f"Rule-fixed: {sum(1 for f in all_formulas if f.rule_fixed)}")
    print(f"LLM-fixed: {sum(1 for f in all_formulas if f.llm_fixed)}")
    print(f"Failed: {sum(1 for f in all_formulas if f.needs_llm and not f.llm_fixed)}")

    # 保存详细报告
    report_path = os.path.join(output_base, 'report.json')
    os.makedirs(output_base, exist_ok=True)
    report = []
    for f in all_formulas:
        report.append({
            'file': f.file_path,
            'line_start': f.line_start,
            'raw_text': f.raw_text,
            'rule_fixed': f.rule_fixed,
            'llm_fixed': f.llm_fixed,
            'related_image': f.related_image,
        })
    with open(report_path, 'w', encoding='utf-8') as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    print(f"Report saved to: {report_path}")


if __name__ == '__main__':
    main()
