"""ローカル検証。重いライブラリやクラウド接続なし。"""
import json
import pathlib
import struct
import sys


def main(args):
    if args[0] == "bucket":
        b, p = (json.loads(pathlib.Path(x).read_text()) for x in args[1:3])
        c = b.get("iamConfiguration", {})
        ubla = b.get("uniform_bucket_level_access", c.get("uniformBucketLevelAccess", {}).get("enabled"))
        pap = b.get("public_access_prevention", c.get("publicAccessPrevention"))
        if b.get("location", "").lower() != args[3] or not ubla or pap != "enforced":
            raise ValueError("既存バケットの地域・非公開設定が不適合。設定を変えず停止")
        if any(m in ("allUsers", "allAuthenticatedUsers") for v in p.get("bindings", []) for m in v.get("members", [])):
            raise ValueError("公開IAMがあるため停止")
        return
    if args[0] == "role":
        r = json.loads(pathlib.Path(args[1]).read_text())
        if r.get("deleted") or set(r.get("includedPermissions", [])) != {"compute.instances.delete"}:
            raise ValueError("自己削除roleの権限不一致")
        return
    out, mode, texture, faces, octree, seed, prepare, folder, prompt = args
    if mode not in ("mv", "single", "text") or texture not in ("on", "off"):
        raise ValueError("mode/textureが不正")
    if prepare not in ("", "env", "weights", "all"):
        raise ValueError("prepare-onlyはenv|weights|all")
    faces, octree, seed = int(faces), int(octree), int(seed)
    if not 1000 <= faces <= 1000000 or octree not in (256, 384, 512) or not 0 <= seed < 2**32:
        raise ValueError("faces=1000〜1000000、octree=256|384|512、seed=uint32")
    views = []
    if not prepare and mode == "text":
        if not prompt and folder:
            prompt = (pathlib.Path(folder) / "prompt.txt").read_text(encoding="utf-8").strip()
        if not prompt or len(prompt) > 2000:
            raise ValueError("textは--promptまたはフォルダ内prompt.txt（1〜2000文字）が必要")
    elif not prepare:
        p = pathlib.Path(folder)
        if not folder or not p.is_dir():
            raise ValueError("画像フォルダが必要")
        for view in ("front", "left", "back", "right"):
            f = p / (view + ".png")
            if f.exists():
                with f.open("rb") as stream:
                    header = stream.read(24)
                if header[:8] != b"\x89PNG\r\n\x1a\n" or len(header) != 24:
                    raise ValueError(f"PNGでない入力: {f.name}")
                w, h = struct.unpack(">II", header[16:24])
                if min(w, h) < 64 or max(w, h) > 8192:
                    raise ValueError("画像寸法は64〜8192px")
                views.append(view)
        if "front" not in views:
            raise ValueError("front.pngが必要（1枚でもよい）")
        if mode == "single":
            views = ["front"]
    effective = mode if prepare else ("mv" if mode == "mv" and len(views) >= 2 else ("text" if mode == "text" else "single"))
    pathlib.Path(out).write_text(json.dumps(dict(mode=effective, requested_mode=mode, texture=texture,
        faces=faces, octree=octree, seed=seed, prepare=prepare, views=views, prompt=prompt), ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, OSError) as e:
        raise SystemExit(str(e)) from e
