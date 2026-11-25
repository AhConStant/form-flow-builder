# 本地补丁清单（升级技能后必须复查）

> 本文件记录**官方包里没有、本地加上去**的修改。每次用新版 zip 覆盖 `C:\Users\54232\.workbuddy\skills\form-flow-builder` 之后，逐条确认还在；不在就按下面重新打。

## P1 · 审批框 / 附件永不带默认值（2026-11-24）

**问题**：`approve` 带 `defVal`/`defaultVal` → 平台前端打不开。`部门领导审核` 里的“部门”命中 dept 规则被绑成 `departmentName`。

**补丁位置**

1. `scripts/build_forms.py` → `field_flags()` 开头：
```python
    if f.get("type") in ("approve", "attachment", "sn", "static", "label", "table"):
        return dict(token=None, user_default=False,
                    dept_default=False, date_default=False)
```
2. `scripts/build_forms.py` → `default_token()` 的 dept 排除词补：
```python
("负责人", "主任", "意见", "审批", "电话", "联系",
 "审核", "领导", "批示", "签发", "会签", "核稿",
 "批准", "确认", "签字")
```
3. `scripts/validate_form.py` → 移动端 `check_mobile()` 内、`isRequire` 校验之后：
```python
        if t in ("approve", "attachment"):
            dv = e["properties"].get("defVal")
            if dv not in (None, ""):
                errs.append("%s %s 不允许带 defVal，实际 %r（审批/附件带默认值会导致前端打不开）"
                            % (where, t, dv))
```
4. `scripts/validate_form.py` → Web 端控件校验里、`showSign` 分支之后：
```python
            if st in ("approve", "attachment") and cell.get("defaultVal") not in (None, ""):
                errs.append("%s %s 不允许带 defaultVal，实际 %r（审批/附件带默认值会导致前端打不开）"
                            % (where, st, cell.get("defaultVal")))
```
5. 文档：`SKILL.md` 默认值那条加半句；`references/field-rules.md` 加「硬规则：审批框/附件永不绑默认值」小节。

## P2 · 「同意执行」默认下一步（2026-11-25）

**问题**：平台里审批节点的「同意执行」默认落到「结束」，必须手选下一步。

**根因**：官方生成器把 `optStep` 写成空、还把 `importantShunt` 整个 pop 掉。平台真实导出件里是：
- `optStep` = `"1"`（判断节点为空串）
- `importantShunt` = 该步骤出线目标的 **DrawID**，多条按顺序逗号分隔（判断节点就是各分支），结束节点为空串

**补丁位置**：`scripts/build_export.py` 的 `build_steps()`，`step.update({...})` 里把

```python
            "optStep": "," * (len(r["to"]) - 1) if node == "nodeJudge" else "",
...
        step.pop("importantShunt", None)
```

改成

```python
            "optStep": "" if node == "nodeJudge" else "1",
            "importantShunt": ",".join(str(t) for t in r["to"]),
```

并删掉 `step.pop("importantShunt", None)` 那一行（连同上方注释）。

**核对基准**（平台导出件 `流程导出_用车流程_v1.0.json`）：
```
开始        optStep=1  importantShunt=2
申请人      optStep=1  importantShunt=3
审批×3      optStep=1  importantShunt=4/5/6
通知执行    optStep=1  importantShunt=7
结束        optStep=1  importantShunt=''
判断(2支)   optStep='' importantShunt='6,5'
```


## P3 · 节点默认开启「退回」（2026-11-25）

**需求**：导入后每个流程节点的「退回设置 → 允许退回」默认是关的，要逐个开。

**补丁位置**：`scripts/build_export.py` 的 `build_steps()`，`step.update({...})` 里加

```python
            "isCanReturn": node not in ("nodeStart", "nodeFirst", "nodeEnd", "nodeJudge"),
```

其余退回项保持平台默认：`returnTrend=0`（退回申请人）、`CanReturnStepID=""`（具体步骤无限制）、
`returnFillBackMode=9` / `returnNotifyAffectedDone=9`（跟系统开关）、`isReturnNeedComment=False`（退回意见非必填）。

平台字段名：退回开关 = `isCanReturn`（不是 `isCanReject`，那个是「不同意」按钮）。

## 无法通过本技能实现的部分（记下来，别再试）

- **流程「权限分配」页（授权对象 / 监控权限 13 项 / 知会权限）不在 `流程导出_*.json` 里**。
  逐键比对平台导出件与本地产物：`FlowSet` 108 键、`FlowSetVersion` 101 键、`FlowSetVersionPart` 42 键**完全一致**（只差 ID/名称/时间戳），全文件搜不到「流程管理员」，也没有 13 位权限布尔数组。
  导出件里唯一与权限有关的只有**附件权限**（`FlowParticipant` 2 条 + `FlowExtraOperation` 2 条，`tabCode=AttachAuthor`），这两处本地生成器已经与平台一致。
  → 权限分配只能在平台「编辑流程 → 权限分配」里配，或等平台提供单独的权限导出格式。
