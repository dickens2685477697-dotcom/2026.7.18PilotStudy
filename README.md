# 2026.7.18 Pilot Study

先导实验的原始数据、历史记录、分析脚本、分析结果与 Unity 实验项目归档。

## 数据位置

| 路径 | 内容 | CSV 文件数 |
| --- | --- | ---: |
| `1/` | 1 号实验记录，含 Cancel 与 Trigger | 145 |
| `2/` | 2 号实验记录，含 Cancel 与 Trigger | 10 |
| `3/` | 3 号实验记录，含 Cancel 与 Trigger | 32 |
| `5/` | 5 号实验记录，含 Cancel 与 Trigger | 64 |
| `旧版/` | 历史版本的实验记录及说明 | 240 |
| `analysis_outputs/` | 已生成的统计表、图像和报告 | 60 |

首次归档共包含 **551 个 CSV 文件**，其中原始及历史实验记录 **491 个**，分析结果 **60 个**。未完成、失败或只有表头的记录也按原样保留。`magictap.txt` 同样纳入归档。`4/`、`6/`、`7/`、`8/`、`9/`、`10/` 在归档时为空，用 `.gitkeep` 保留目录位置。

## 项目与分析

- `analysis/`：Python 分析与绘图脚本；常用第三方依赖为 NumPy、pandas、Matplotlib，可通过 `python -m pip install numpy pandas matplotlib` 安装。各脚本的参数请查看相应源文件。
- `analysis_outputs/`：现有分析结果，连同原始数据一起保存。
- `HLStudy4_22_speed_exit_logging/`：Unity 实验项目、资源、配置、项目文档与输出。`ProjectSettings/ProjectVersion.txt` 记录的 Unity 版本为 `2020.3.37f1c1`。

Unity 目录在原计算机上是另一个仓库的 Git worktree。本仓库保存其实际文件快照，不依赖原计算机的 `.git` 指针，也不使用子模块。

## 数据完整性核验

`DATA_MANIFEST.csv` 记录所有 CSV 文件及 `magictap.txt` 的相对路径、类别、原始字节数和 SHA-256。克隆仓库后，可在仓库根目录执行：

```powershell
python tools/verify_data.py
```

脚本还会检查是否存在未列入清单的 CSV 文件。新增或有意修改数据后，可更新清单再提交：

```powershell
python tools/verify_data.py --write
```

`.gitattributes` 保留文件原始字节，不做换行转换。所有数据文件直接存储在 Git 中。忽略项仅包括本地 Python 依赖目录、缓存、运行日志、凭据文件，以及 Unity 项目自身已有忽略规则覆盖的生成文件。
