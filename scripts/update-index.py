# -*- coding: utf-8 -*-
"""DSH 插件市场索引自动更新脚本（GitHub Actions 云端运行版）。

链路：下载 dsh.market 全量 → 筛选真 DSH 插件 → 按 star 取 Top80 →
      用 GitHub API 解析每个仓库的默认分支 HEAD commit SHA → 生成 format-1 索引。

结构对齐 @deepseek-ai/dsh-plugin-market-index@0.2.1-rc.2 校验器要求：
  顶层 {format:1, title, description, plugins:[...]}；
  plugins[i] = {name, title{en,zh}, description{en,zh}, author, homepage,
                repository{url}, versions:[{version, publishTimestamp, source{type,url,commit}, engines}]}

已知坑（勿重犯）：
  - 用字符串拼接生成 JSON 时，顶层对象结尾的 "}" 会提前闭合，导致 plugins 数组被拼到
    对象外部，jsDelivr 严格解析报 "Extra data"。本脚本用 json.dumps 整体序列化，天然规避。
  - 公共 GitHub API 限流 60 次/小时，80+ 仓库会触发 403；在 Actions 中用 GITHUB_TOKEN
    （1000 次/小时）解析，本地无 token 时降级公共 API 并提示。
"""
import json, os, sys, re, time, io, datetime, urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MARKET_URL = "https://dsh.market/plugins.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugins.json")
TOP_N = 80
CANDIDATE_POOL = 150          # 候选池略大于 Top80，剔除解析失败项后仍能凑满
UA = "Mozilla/5.0 (dsh-plugin-index-builder; +github.com/stellvyr/dsh-plugin-index)"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(dst)


def api(url):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def head_commit(repo_url, cache):
    """返回仓库默认分支 HEAD commit SHA（40 位小写 hex），失败返回 None。"""
    if repo_url in cache:
        return cache[repo_url]
    owner, name = repo_url.replace("https://github.com/", "").split("/", 1)
    try:
        data = api(f"https://api.github.com/repos/{owner}/{name}/commits?per_page=1")
        if isinstance(data, list) and data and data[0].get("sha"):
            sha = data[0]["sha"]
            if SHA_RE.match(sha):
                cache[repo_url] = sha
                return sha
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            time.sleep(2)
            return None
        # 404/301 等：仓库不存在/被改名/已删除，跳过
    except Exception:
        pass
    return None


def ts_from_iso(s):
    try:
        return int(datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 1700000000


def main():
    print(f"[1/5] downloading {MARKET_URL} ...")
    market = "dsh-market-full.json"
    size = download(MARKET_URL, market)
    print(f"      downloaded {size} bytes")

    print("[2/5] parsing & filtering ...")
    with open(market, "r", encoding="utf-8") as f:
        data = json.load(f)
    plugs = data.get("plugins", [])
    real = [
        p for p in plugs
        if any(str(c).strip().startswith("dsh plugin ") and "add github:" in str(c)
               for c in ((p.get("install") or {}).get("commands") or []))
    ]
    print(f"      total={len(plugs)} real_dsh={len(real)}")

    real.sort(key=lambda p: p.get("stars") or 0, reverse=True)
    pool = real[:CANDIDATE_POOL]
    print(f"[3/5] resolving HEAD commits for {len(pool)} candidates ...")

    cache = {}
    sel = []
    for p in pool:
        full = p.get("fullName") or p.get("id") or ""
        if "/" not in full:
            continue
        owner, repo = full.split("/", 1)
        git_url = f"https://github.com/{owner}/{repo}"
        sha = head_commit(git_url, cache)
        if not sha:
            print(f"      skip {git_url} (no resolvable commit)")
            continue
        sel.append((p, sha))
        print(f"      ok {git_url} -> {sha[:12]}")
        if len(sel) >= TOP_N:
            break

    print(f"[4/5] building format-1 index ({len(sel)} plugins) ...")
    plugins_out = []
    for p, sha in sel:
        full = p.get("fullName") or p.get("id") or ""
        owner, repo = full.split("/", 1)
        desc_en = p.get("description") or ""
        desc_zh = p.get("descriptionZh") or ""
        homepage = p.get("homepage") or f"https://github.com/{full}"
        git_url = f"https://github.com/{owner}/{repo}"
        ts = ts_from_iso(p.get("pushedAt") or "")
        name = f"@{owner.lower()}/{repo.lower()}"
        plugins_out.append({
            "name": name,
            "title": {"en": repo, "zh": repo},
            "description": {
                "en": (desc_en[:500] or "DeepSeek Harness plugin"),
                "zh": (desc_zh[:500] or "DeepSeek Harness 插件"),
            },
            "author": owner,
            "homepage": homepage,
            "repository": {"url": git_url},
            "versions": [{
                "version": "0.1.0",
                "publishTimestamp": ts,
                "source": {"type": "git", "url": git_url, "commit": sha},
                "engines": {"dsh": (p.get("install") or {}).get("dshEngines") or ">=0.1.0"},
            }],
        })

    index = {
        "format": 1,
        "title": {"en": "DSH Community Top Plugins", "zh": "DSH 社区精选插件"},
        "description": {
            "en": f"Top {len(plugins_out)} community plugins by stars, converted from dsh.market",
            "zh": f"按 star 精选的 {len(plugins_out)} 个社区插件（源自 dsh.market 目录）",
        },
        "plugins": plugins_out,
    }

    out = os.path.normpath(OUT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"[5/5] wrote {out} ({os.path.getsize(out)} bytes, {len(plugins_out)} plugins)")
    with open(out, "r", encoding="utf-8") as f:
        check = json.load(f)
    assert check.get("format") == 1, "format must be 1"
    assert isinstance(check.get("plugins"), list), "plugins must be a list"
    bad = [x["name"] for x in check["plugins"]
           if not SHA_RE.match(x["versions"][0]["source"].get("commit", ""))]
    assert not bad, f"bad commits: {bad}"
    print("      self-check OK: format=1, plugins=%d, all commits 40-hex" % len(check["plugins"]))
    if not TOKEN:
        print("      WARNING: no GITHUB_TOKEN, used public API (rate limit may bite)")


if __name__ == "__main__":
    main()
