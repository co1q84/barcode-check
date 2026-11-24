---
name: 条码核验
description: Windows 桌面核验工具的浅色界面规范
colors:
  primary: "#235BB7"
  primary-active: "#194C9F"
  primary-soft: "#EAF1FC"
  success: "#176347"
  success-soft: "#E9F5EF"
  warning: "#8B4B10"
  warning-soft: "#FFF3DE"
  scan-alert-warning: "#FFE6BB"
  error: "#A42932"
  error-soft: "#FCEDEF"
  scan-alert-error: "#FFDBDF"
  canvas: "#F4F6FA"
  surface: "#FFFFFF"
  border: "#D6DFEB"
  text: "#17263B"
  muted: "#53637A"
  table-heading: "#EAF0F8"
  progress-track: "#DCE6F6"
typography:
  quantity:
    fontFamily: Microsoft YaHei UI
    fontSize: "34.6667px"
    fontWeight: 700
  section:
    fontFamily: Microsoft YaHei UI
    fontSize: "16px"
    fontWeight: 700
  scan:
    fontFamily: Microsoft YaHei UI
    fontSize: "16px"
    fontWeight: 400
  feedback-body:
    fontFamily: Microsoft YaHei UI
    fontSize: "24px"
    fontWeight: 400
  feedback-manufacturer:
    fontFamily: Microsoft YaHei UI
    fontSize: "32px"
    fontWeight: 700
  table-heading:
    fontFamily: Microsoft YaHei UI
    fontSize: "13.3333px"
    fontWeight: 700
  body:
    fontFamily: Microsoft YaHei UI
    fontSize: "13.3333px"
    fontWeight: 400
spacing:
  control-y: "6px"
  control-gap: "8px"
  compact-section: "10px"
  section-gap: "12px"
  settings-inset: "16px"
  main-inset-x: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    padding: "6px 11px"
  button-standard:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    padding: "6px 11px"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.error}"
    padding: "6px 11px"
  text-entry:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    padding: "6px 8px"
  scan-entry:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.scan}"
    padding: "9px 10px"
  scan-feedback:
    typography: "{typography.feedback-body}"
    padding: "5px 10px"
  table-heading:
    backgroundColor: "{colors.table-heading}"
    textColor: "{colors.text}"
    typography: "{typography.table-heading}"
    padding: "6px 7px"
---

## Overview

**Creative North Star: "连续扫码"**

浅灰底上用白色区域分开填写、扫码和读数。作业员视线沿核验目标、扫码结果、记录自然下移，主操作和键盘焦点共用蓝色。设置沿用白底、浅灰表头和同一套控件。视觉取值对应 [Tkinter 主题](barcode_check/theme.py)。

**Key Characteristics**

- 核验目标固定在顶部，扫码框和有效数量并排。
- 扫码框下方显示最近一次结果，异常原因随记录保留。
- 常规 Windows 窗口支持缩放和最大化，新增空间优先给记录表。

## Colors

- **操作蓝** `primary` 用于主按钮、焦点边线、选中页签文字和进度填充。`primary-active` 用于主按钮悬停和按下，`primary-soft` 用于普通按钮悬停、表格选中和提示条。
- **状态色** 用绿色报告通过和数量已齐，用暖棕提示重复条码和结束时数量不足，用红色呈现拦截原因和删除操作。扫码区与数量区在异常时同步使用 `scan-alert-warning` 或 `scan-alert-error`，并保留具体原因。通过后恢复白底。
- **中性色** `canvas` 是窗口浅灰底，`surface` 是白色内容及输入区。深色 `text` 承载标题、值和结果，`muted` 承载说明及禁用文字。表头略深于背景，`border` 用于控件细边线。

## Typography

统一使用 Microsoft YaHei UI。Tk 正文字号为 10 pt，普通控件和辅助说明共用这一字号，表头加粗。区块标题为 12 pt 粗体，扫码输入为 12 pt 常规体，有效数量为 26 pt 粗体。前置 token 的像素值按 96 DPI 换算，实际字体和行高由 Tk 跟随系统设置计算。

## Layout

- **主窗口** 初始宽度最多 1100，最小客户区 820 × 580。优先按记录表可见 20 行计算初始高度，屏幕较矮时限制窗口高度，表内滚动。顶部核验目标与设置入口共用一区。扫码在左，有效数量、差额及进度在右。记录表填充其余空间，条码、厂家和说明列吸收横向空间。表格底部左侧显示页码及记录范围，右侧可调整每页条数及翻页。选中记录后，表格下方显示完整条码、厂家及说明。见 [主窗口布局](barcode_check/app.py)。
- **设置窗口** 单张条码基表展示编码、厂家和条码前缀。标题与搜索框在顶部，工具栏左侧为新增、编辑和批量删除，右侧为 Excel 导入数据、导出数据和导出模板。底部显示筛选、选择数量和操作结果。初始 880 × 550、最小 680 × 400，按 DPI 和屏幕空间调整。见 [设置窗口布局](barcode_check/settings_ui.py)。

## Elevation & Depth

内容采用平面分区。浅灰窗口底衬托白色工作区，细描边、分隔线和表头底色划定边界。应用窗口和模态窗口沿用 Windows 标题栏。

## Shapes

Tkinter `clam` 控件采用直角矩形与细边线。信息区域、扫码反馈、表头和进度条横向对齐。焦点通过描边变蓝呈现，选中行通过底色切换呈现。

## Components

- **按钮** 蓝底白字用于开始、结束、新建批次和确认等当前主操作。普通按钮为白底、深色文字，删除按钮复用普通按钮外形并使用红字。禁用按钮在浅灰底上用灰色文字。
- **字段** 标签保留在输入框外。普通输入和只读下拉用白底，禁用时用浅灰底。扫码框增加字号及留白，接收回车提交。核验中弹窗关闭后恢复扫码焦点，主窗也可按 F2 返回该框。
- **扫码反馈与数量** 扫码结果在提示区水平、垂直居中，较长内容可换行。核验通过时显示厂家与条码，厂家不符时显示目标厂家与识别厂家。厂家名称为 24 pt 粗体，提示说明为 18 pt。右侧显示有效数量，有应扫目标时显示比值、差额和进度条，齐数时显示「数量已齐」。未设数量时显示件数及「未设应扫数量」。每次扫码异常或出现数量不足提示时播放一次 Windows 系统异常提示音。
- **表格** 浅蓝灰表头配粗体，数据左对齐，选中行使用浅蓝底。记录按新增倒序，默认接受项用常规文字，重复和拦截行用浅状态底搭配结果与说明列。设置列表允许多选，工具栏可用状态随选中数量变化。
- **异常弹窗** 超量弹窗用红色标题，正文列出应扫数量、当前有效数量和本次条码。扫码输入暂停，继续按钮把作业员带回扫码流程。

## Do's and Don'ts

- 保留扫码框、最近结果和有效数量在同一视线范围内。
- 状态色始终配合可读的状态词或原因，缩小窗口时仍可选中记录查看完整说明。
- 让记录表吸收窗口高度变化，让条码、厂家和说明列吸收宽度变化。

`.impeccable/design.json` 中的控件片段用于 Impeccable 文档预览，桌面应用由 Tkinter 渲染。色带是面板的展示辅助，实际配色以本文件上方的取值为准。
