# Git 分支工作流

## Git 的存储模型

Git 是内容寻址的版本库：每次提交（commit）生成一个包含树对象、父提交引用、提交信息的快照；文件内容以 blob 对象存储，对象名是内容的 SHA-1/SHA-256 哈希。分支只是一个指向某次提交的**可变指针**，创建分支几乎零成本——这决定了 Git 鼓励频繁开分支的用法。`HEAD` 指向当前所在分支，`git checkout <commit>` 会让 HEAD 进入 detached 状态（分离头指针），此时的新提交不会被任何分支引用。

## 分支操作

- `git branch feature` 创建分支（指针指向当前提交）；
- `git switch feature` 或 `git checkout feature` 切换分支（切换时工作区文件被替换为目标分支版本）；
- `git merge feature` 把 feature 合入当前分支：能快进（fast-forward）时直接移动指针，否则创建合并提交；
- `git rebase main` 把当前分支的提交"重放"到 main 最新提交之上，历史呈线性，但会改写提交哈希——**绝不要 rebase 已推送到共享仓库的分支**；
- `git cherry-pick <commit>` 单独摘取某次提交到当前分支。

## 主流工作流

1. **GitHub Flow**：main 分支永远可部署；任何改动开 feature 分支，完成后发 Pull Request（PR），评审通过后合入并部署。最简单，适合持续部署的团队。
2. **Git Flow**：main（发布分支）+ develop（集成分支）+ feature/release/hotfix 分支。规范重，适合有明确版本发布节奏的产品。
3. **GitLab Flow**：环境分支（main → staging → production 依次合并或部署），把"哪个环境跑了什么代码"显式化。

## 冲突解决

两个分支修改同一文件的同一区域时合并冲突。解决流程：`git status` 定位冲突文件，打开文件找到 `<<<<<<< ======= >>>>>>>` 标记，保留想要的代码删除标记，`git add` 标记已解决，最后 `git commit` 完成合并。减少冲突的手段：小步提交、频繁同步 main、职责单一的分支。

## 撤销操作

- `git reset --soft HEAD~1` 撤销提交但保留改动在暂存区；
- `git reset --mixed HEAD~1`（默认）撤销提交且移出暂存区，改动留在工作区；
- `git reset --hard HEAD~1` 撤销提交并**丢弃**改动（危险，不可恢复）；
- `git revert <commit>` 生成一个"反向提交"抵消历史提交，适合撤销已推送的提交（不改写历史）；
- `git stash` 暂存未提交改动，`git stash pop` 恢复。

## 团队协作要点

- 提交信息用约定式提交（Conventional Commits）：`feat: 新增检索接口`、`fix: 修复分块越界`；
- `.gitignore` 排除环境文件与产物，密钥（.env）绝不入库——历史中泄露的密钥即使删除文件也仍可被翻出，必须作废密钥；
- 推送前 `git pull --rebase` 保持线性历史，减少无意义的合并提交。
