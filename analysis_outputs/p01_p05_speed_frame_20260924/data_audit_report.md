# P01 / P05 数据审计报告

## 1. 文件发现

- P01：原始目录下共 145 个 CSV；Trigger 15 个 run，Cancel 15 个 run。
- P05：原始目录下共 64 个 CSV；Trigger 15 个 run，Cancel 目录为空。
- Speed 系列逐帧主分析：384 个 trial（2 人 × 4 技术 × 3 尺寸 × 16 trial）。
- 逐文件行数、字段、可用 timestamp 范围与估计采样率见 `file_audit.csv`。

## 2. 字段定义（由代码与日志交叉确认）

- participant：顶层目录 `1`/`5`，报告中写为 P01/P05。
- technique：`time.csv` 与 `trajectory.csv` 的 `modeSelected`；本分析使用日志原名 speed、speedDwell、speedRelease、speedDirection。工作区没有 Speed-Motion/Speed-Gesture 这两个字符串，因此不擅自改名。
- trial：`ID × Case` 唯一定位；每个 run 正式记录 3 个 ID × 16 个 Case。
- target size：场景 `idLogicMode=New`，ID 1/2/3 映射到旧 ID 1/5/9，因此分别为 Large 直径 0.09 m、Medium 0.06 m、Small 0.03 m。
- finger position：trajectory 的 indexLocX/Y/Z，为 Unity 世界坐标中的食指尖位置。Unity 场景尺度与阈值注释均表明单位为米。
- target center：time.csv 在前 26 列之后记录 largeCirclePoint 与 16 个逐球心坐标；目标球心取 ballIndex+1 的坐标三元组。目标在 trial 内静止；仍逐帧使用该 trial 球心计算 rho。
- inside target：实验程序用 Collider.bounds.Contains，即轴对齐包围盒，且 tip 或 distal 任一进入即可；本分析按用户要求另算食指尖球面 rho<=1。两者不等价。
- trigger/success：time.csv 的 triggerCondition='S' 表示 Speed 成功完成；所有 Speed trial 最终均有 S。time.csv 只在完成时写一行，所以它不包含被放弃的未完成 trial。
- timestamp：trajectory.csv 没有 timestamp 或 frame。direction-debug / pinch-release-distance 等事件日志有 Unity Time.time 秒，但 Speed 原始 run 没有 speed-boundary-debug 文件。

## 3. Speed 阈值与算法

- 保留的 Study3SelectionSettings 与 study3 场景配置：speedMinThreshold=0.067 m/s，speedMaxThreshold=0.375 m/s；pressSpeedThershold=0.4 m/s 属于 Press，不是四个 Speed 模式的主阈值。
- 速度为相邻 FixedUpdate 指尖位置差的欧氏长度 / Time.fixedDeltaTime，是非负速度大小，不带方向、未平滑、单帧瞬时值。
- 当前代码的四个 Speed 模式均要求：进入后先观察到 speed<=0.067（armed），随后在目标内某一帧 speed>=0.375 才触发。没有要求连续多帧超过最大阈值。
- 进入前的上一帧位置参与进入帧速度计算，因为速度先由当前/上一 FixedUpdate 位置计算，再执行 inside 与阈值逻辑。
- ProjectSettings/TimeManager.asset 的 Fixed Timestep=0.02 s（名义 50 Hz），但轨迹日志未保存真实 timestamp；因此脚本重算速度/加速度只能作为名义时间敏感性分析，不能验证真实帧间抖动或丢帧。

## 4. 数据质量

- Speed run 的 trial 汇总完整：384/384；每个参与者每个 Speed 技术 48 行。
- 球面 rho 派生进入次数与程序记录 inTargetTimes 不一致的 trial：113/384（原因包括 AABB vs 球面、distal joint 未记录以及逐帧边界采样）。
- 大于 5 cm 的相邻位置跳变总数：810；逐 trial 明细见 trial_metrics.csv。
- trajectory 无 timestamp，故缺失帧、重复 timestamp、非单调 timestamp无法直接审计；事件日志中有 timestamp 的文件已在 file_audit.csv 单独检查。
- P05 的 dwell run 有 49 条 time 行而非 48；已有分析曾将额外行排除并留审计。Speed run 均为 48。
- P05 Speed 数据采集于 2026-08-29，P01 于 2026-08-30；字段结构、ID 结构、模式集合相同。没有构建号/APK 哈希，不能严格证明二进制版本相同；只能说 schema 与保留配置一致。

## 5. 单位与坐标系

- 位置/球直径/路径长度：米；速度：米/秒；加速度：米/秒²；角度：度；Time.time/usedTime/triggerTime：秒。
- 坐标是 Unity 左手世界坐标（x 右、y 上、z 前为 Unity 约定）；日志未记录头部姿态，无法转换成严格的头坐标系。
- 三维代表轨迹先平移到球心、除以半径，再把进入方向旋转到 +x，避免未对齐意大利面图。
