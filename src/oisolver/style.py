"""Lightweight C++ patch minimality and style-preservation metrics."""
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


CPP_TOKEN = re.compile(
    r"//[^\n]*|/\*.*?\*/|(?:u8|u|U|L)?\"(?:\\.|[^\"\\])*\"|"
    r"(?:u8|u|U|L)?'(?:\\.|[^'\\])*'|[A-Za-z_]\w*|"
    r"(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?)|"
    r"::|->|<<=|>>=|==|!=|<=|>=|&&|\|\||\+\+|--|<<|>>|"
    r"\+=|-=|\*=|/=|%=|&=|\|=|\^=|[{}()\[\];,.?:~!%^&*+=|<>/-]",
    re.DOTALL,
)
IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")
KEYWORDS = frozenset({
    "alignas", "alignof", "and", "asm", "auto", "bool", "break", "case",
    "catch", "char", "class", "const", "constexpr", "continue", "decltype",
    "default", "delete", "do", "double", "else", "enum", "explicit", "extern",
    "false", "float", "for", "friend", "goto", "if", "inline", "int", "long",
    "namespace", "new", "noexcept", "not", "nullptr", "operator", "or", "private",
    "protected", "public", "register", "return", "short", "signed", "sizeof",
    "static", "struct", "switch", "template", "this", "throw", "true", "try",
    "typedef", "typename", "union", "unsigned", "using", "virtual", "void",
    "volatile", "while",
})


class StyleError(ValueError):
    pass


def cpp_tokens(text: str, include_comments: bool = False) -> List[str]:
    tokens = CPP_TOKEN.findall(text)
    if include_comments:
        return tokens
    return [token for token in tokens
            if not token.startswith("//") and not token.startswith("/*")]


def _levenshtein(left: Sequence[str], right: Sequence[str], exact_limit: int = 5000) -> Tuple[int, bool]:
    if len(left) * len(right) > exact_limit * exact_limit:
        matcher = difflib.SequenceMatcher(a=left, b=right, autojunk=False)
        matches = sum(block.size for block in matcher.get_matching_blocks())
        return max(len(left), len(right)) - matches, False
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row, right_item in enumerate(right, 1):
        current = [row]
        for column, left_item in enumerate(left, 1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_item != right_item),
            ))
        previous = current
    return previous[-1], True


def _changed_line_count(before: str, after: str) -> int:
    left, right = before.splitlines(), after.splitlines()
    changed = 0
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(
            a=left, b=right, autojunk=False).get_opcodes():
        if tag != "equal":
            changed += max(a2 - a1, b2 - b1)
    return changed


def _declared_identifiers(text: str) -> List[str]:
    pattern = re.compile(
        r"\b(?:int|long\s+long|short|char|bool|double|float|auto|size_t|"
        r"vector\s*<[^;{}]+>|string|map\s*<[^;{}]+>|set\s*<[^;{}]+>)"
        r"\s*(?:[&*]\s*)?([A-Za-z_]\w*)"
    )
    return pattern.findall(text)


def _all_identifiers(tokens: Sequence[str]) -> List[str]:
    return [token for token in tokens
            if IDENTIFIER.match(token) and token not in KEYWORDS]


def _macro_map(text: str) -> Dict[str, str]:
    result = {}
    for line in text.splitlines():
        match = re.match(r"^\s*#\s*define\s+([A-Za-z_]\w*)(.*)$", line)
        if match:
            result[match.group(1)] = match.group(2).strip()
    return result


def _global_array_count(text: str) -> int:
    declaration = re.compile(
        r"^\s*(?:static\s+)?(?:int|long\s+long|char|double|bool)\s+"
        r"[A-Za-z_]\w*\s*\[[^\n;]+\]"
    )
    depth = 0
    count = 0
    for line in text.splitlines():
        if depth == 0 and declaration.match(line):
            count += 1
        for token in cpp_tokens(line):
            if token == "{":
                depth += 1
            elif token == "}":
                depth = max(0, depth - 1)
    return count


def _indentation_preservation(before: str, after: str) -> float:
    left = before.splitlines()
    right = after.splitlines()
    left_shape = [line.lstrip(" \t") for line in left]
    right_shape = [line.lstrip(" \t") for line in right]
    compared = preserved = 0
    for a, b, size in difflib.SequenceMatcher(
            a=left_shape, b=right_shape, autojunk=False).get_matching_blocks():
        for offset in range(size):
            if not left_shape[a + offset]:
                continue
            compared += 1
            left_indent = left[a + offset][:-len(left[a + offset].lstrip(" \t"))]
            right_indent = right[b + offset][:-len(right[b + offset].lstrip(" \t"))]
            preserved += left_indent == right_indent
    return 1.0 if compared == 0 else preserved / compared


def _ratio_retained(before: Iterable[str], after: Iterable[str]) -> float:
    before_set = set(before)
    after_set = set(after)
    return 1.0 if not before_set else len(before_set & after_set) / len(before_set)


def _structural_signature(tokens: Sequence[str]) -> List[str]:
    signature = []
    control = {"if", "for", "while", "switch", "catch", "return"}
    for index, token in enumerate(tokens):
        if token in control:
            signature.append("Control:" + token)
        elif token == "{":
            signature.append("ScopeStart")
        elif token == "}":
            signature.append("ScopeEnd")
        elif (IDENTIFIER.match(token) and index + 1 < len(tokens)
              and tokens[index + 1] == "("):
            signature.append("Callable:" + token)
    return signature


def clang_ast_signature(source: Path, clang: str = "clang++",
                        standard: str = "c++17", timeout: float = 15.0) -> Dict[str, Any]:
    executable = shutil.which(clang) if not Path(clang).is_file() else clang
    if executable is None:
        return {"available": False, "reason": "clang++ not found", "nodes": []}
    try:
        process = subprocess.run(
            [str(executable), "-std={}".format(standard), "-fsyntax-only",
             "-Xclang", "-ast-dump=json", str(source)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": str(exc), "nodes": []}
    if process.returncode != 0:
        return {"available": False,
                "reason": process.stderr.decode("utf-8", errors="replace")[:1000],
                "nodes": []}
    try:
        tree = json.loads(process.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": str(exc), "nodes": []}
    nodes: List[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        kind = node.get("kind")
        if isinstance(kind, str):
            nodes.append(kind)
        for child in node.get("inner", []):
            walk(child)

    walk(tree)
    return {"available": True, "backend": "clang-json", "nodes": nodes}


def evaluate_cpp_patch(before: str, after: str,
                       expected_replacements: Sequence[Tuple[str, str]] = (),
                       before_path: Optional[Path] = None,
                       after_path: Optional[Path] = None,
                       clang: Optional[str] = None,
                       max_nonessential_line_rate: float = 0.10) -> Dict[str, Any]:
    for replacement in expected_replacements:
        if (not isinstance(replacement, (list, tuple)) or len(replacement) != 2
                or any(not isinstance(item, str) or not item for item in replacement)):
            raise StyleError("expected_replacements must contain nonempty string pairs")
    if not 0 <= max_nonessential_line_rate <= 1:
        raise StyleError("max_nonessential_line_rate must be within [0,1]")

    before_tokens = cpp_tokens(before)
    after_tokens = cpp_tokens(after)
    token_distance, exact = _levenshtein(before_tokens, after_tokens)
    token_denominator = max(1, len(before_tokens), len(after_tokens))
    token_rate = token_distance / token_denominator
    changed_lines = _changed_line_count(before, after)
    line_denominator = max(1, len(before.splitlines()), len(after.splitlines()))

    expected = before
    for old, new in expected_replacements:
        expected = expected.replace(old, new)
    nonessential_lines = _changed_line_count(expected, after)
    nonessential_rate = nonessential_lines / line_denominator

    before_identifiers = _all_identifiers(before_tokens)
    expected_identifiers = _all_identifiers(cpp_tokens(expected))
    after_identifiers = _all_identifiers(after_tokens)
    raw_identifier_retention = _ratio_retained(before_identifiers, after_identifiers)
    identifier_retention = _ratio_retained(expected_identifiers, after_identifiers)
    before_variables = _declared_identifiers(before)
    expected_variables = _declared_identifiers(expected)
    after_variables = _declared_identifiers(after)
    raw_variable_retention = _ratio_retained(before_variables, after_variables)
    variable_retention = _ratio_retained(expected_variables, after_variables)
    expected_macros, after_macros = _macro_map(expected), _macro_map(after)
    exact_macros = [name for name, body in expected_macros.items()
                    if after_macros.get(name) == body]
    macro_retention = (1.0 if not expected_macros else
                       len(exact_macros) / len(expected_macros))
    indentation_retention = _indentation_preservation(before, after)
    before_blank = sum(not line.strip() for line in before.splitlines())
    after_blank = sum(not line.strip() for line in after.splitlines())
    blank_retention = (1.0 if before_blank == 0 else
                       max(0.0, 1.0 - abs(before_blank - after_blank) / before_blank))

    fast_io_markers = ("ios::sync_with_stdio", "cin.tie", "getchar", "fread")
    removed_fast_io = [marker for marker in fast_io_markers
                       if marker in expected and marker not in after]
    arrays_before = _global_array_count(before)
    arrays_expected = _global_array_count(expected)
    arrays_after = _global_array_count(after)
    global_array_retention = (1.0 if arrays_expected == 0 else
                              min(1.0, arrays_after / arrays_expected))
    vectors_before = len(re.findall(r"\bvector\s*<", before))
    vectors_expected = len(re.findall(r"\bvector\s*<", expected))
    vectors_after = len(re.findall(r"\bvector\s*<", after))

    structural_before = _structural_signature(before_tokens)
    structural_after = _structural_signature(after_tokens)
    structural_distance, structural_exact = _levenshtein(
        structural_before, structural_after
    )
    structural_denominator = max(1, len(structural_before), len(structural_after))
    ast_report: Dict[str, Any] = {
        "lightweight_backend": "structural-token-tree",
        "edit_distance": structural_distance,
        "normalized_edit_distance": structural_distance / structural_denominator,
        "exact": structural_exact,
        "compiler_ast": {"available": False, "reason": "clang backend not requested"},
    }
    if clang is not None:
        if before_path is None or after_path is None:
            raise StyleError("clang AST comparison requires before_path and after_path")
        left_ast = clang_ast_signature(before_path, clang)
        right_ast = clang_ast_signature(after_path, clang)
        compiler_ast: Dict[str, Any] = {
            "available": left_ast["available"] and right_ast["available"],
            "before_reason": left_ast.get("reason", ""),
            "after_reason": right_ast.get("reason", ""),
        }
        if compiler_ast["available"]:
            distance, ast_exact = _levenshtein(left_ast["nodes"], right_ast["nodes"])
            denominator = max(1, len(left_ast["nodes"]), len(right_ast["nodes"]))
            compiler_ast.update({"edit_distance": distance,
                                 "normalized_edit_distance": distance / denominator,
                                 "exact": ast_exact,
                                 "before_nodes": len(left_ast["nodes"]),
                                 "after_nodes": len(right_ast["nodes"])})
        ast_report["compiler_ast"] = compiler_ast

    warnings: List[Dict[str, str]] = []

    def warning(code: str, message: str, severity: str = "warning") -> None:
        warnings.append({"code": code, "message": message, "severity": severity})

    if nonessential_rate > max_nonessential_line_rate:
        warning("NONESSENTIAL_LINE_CHANGES",
                "Non-authorized line change rate {:.3f} exceeds {:.3f}.".format(
                    nonessential_rate, max_nonessential_line_rate), "error")
    if identifier_retention < 0.90:
        warning("IDENTIFIERS_NOT_PRESERVED",
                "Only {:.1%} of C++ identifiers were retained.".format(
                    identifier_retention), "error")
    if variable_retention < 0.90:
        warning("VARIABLE_NAMES_NOT_PRESERVED",
                "Only {:.1%} of declared variable names were retained.".format(
                    variable_retention), "error")
    if macro_retention < 1.0:
        warning("MACRO_CHANGED_OR_REMOVED", "A pre-existing macro changed or disappeared.",
                "error")
    if indentation_retention < 0.90:
        warning("INDENTATION_DRIFT",
                "Indentation retention fell below 90%.", "warning")
    if removed_fast_io:
        warning("FAST_IO_REMOVED", "Fast-I/O constructs were removed: {}".format(
            ", ".join(removed_fast_io)), "error")
    if arrays_after < arrays_expected and vectors_after > vectors_expected:
        warning("GLOBAL_ARRAY_REPLACED_BY_VECTOR",
                "A global array appears to have been replaced by vector.", "error")

    fast_io_retention = 1.0 if not removed_fast_io else 0.0
    score = 100.0 * (
        0.25 * (1.0 - min(1.0, token_rate))
        + 0.20 * (1.0 - min(1.0, nonessential_rate))
        + 0.10 * identifier_retention
        + 0.05 * variable_retention
        + 0.10 * macro_retention
        + 0.08 * indentation_retention
        + 0.04 * blank_retention
        + 0.05 * (1.0 - min(1.0, structural_distance / structural_denominator))
        + 0.06 * fast_io_retention
        + 0.07 * global_array_retention
    )
    return {
        "schema_version": 1,
        "token": {
            "before": len(before_tokens),
            "after": len(after_tokens),
            "edit_distance": token_distance,
            "normalized_edit_distance": token_rate,
            "exact": exact,
        },
        "ast": ast_report,
        "lines": {
            "changed": changed_lines,
            "nonessential_changed": nonessential_lines,
            "nonessential_change_rate": nonessential_rate,
        },
        "preservation": {
            "identifiers": identifier_retention,
            "variable_names": variable_retention,
            "raw_identifiers_before_authorization": raw_identifier_retention,
            "raw_variable_names_before_authorization": raw_variable_retention,
            "macros": macro_retention,
            "indentation": indentation_retention,
            "blank_lines": blank_retention,
            "fast_io": fast_io_retention,
            "global_arrays": global_array_retention,
        },
        "signals": {
            "global_arrays_before": arrays_before,
            "global_arrays_after_authorized_replacements": arrays_expected,
            "global_arrays_after": arrays_after,
            "vectors_before": vectors_before,
            "vectors_after_authorized_replacements": vectors_expected,
            "vectors_after": vectors_after,
        },
        "warnings": warnings,
        "gate_passed": not any(item["severity"] == "error" for item in warnings),
        "score": round(score, 3),
        "claim_status": "TESTED_ONLY",
        "claim_boundary": "These syntactic metrics cannot decide whether a larger semantic change was necessary.",
    }


def evaluate_cpp_files(before_path: Path, after_path: Path,
                       expected_replacements: Sequence[Tuple[str, str]] = (),
                       clang: Optional[str] = None,
                       max_nonessential_line_rate: float = 0.10) -> Dict[str, Any]:
    before_path = before_path.resolve(strict=True)
    after_path = after_path.resolve(strict=True)
    return evaluate_cpp_patch(
        before_path.read_text(encoding="utf-8"),
        after_path.read_text(encoding="utf-8"),
        expected_replacements,
        before_path,
        after_path,
        clang,
        max_nonessential_line_rate,
    )
