# 贡献指南

感谢你对PokePilot项目的兴趣！本文档将指导你如何为项目做出贡献。

## 如何开始

### 报告Bug

在提交Bug报告之前，请搜索现有的Issue，确保问题未被报告过。

提交Bug时，请包含：
- **清晰的标题和描述**
- **具体的步骤来重现问题**
- **你的环境信息**：操作系统、Python版本、依赖版本
- **错误日志或截图**（如果适用）
- **实际结果 vs 预期结果**

示例：
```
标题：[BUG] 在Windows上init.ps1脚本执行失败

步骤：
1. 运行 powershell -ExecutionPolicy Bypass -File init.ps1
2. ...

预期：脚本应该完成初始化
实际：在第3步时报错 xxx

环境：
- Windows 11
- Python 3.11.5
- Git Bash
```

### 建议新功能

如果你有新功能的想法：
1. 先创建一个Issue描述你的想法
2. 在Issue中讨论实现方式
3. 等待反馈后再开始实现

## 开发环境设置

### 1. Fork和克隆

```bash
# Fork项目（GitHub UI操作）
# 然后克隆你的fork
git clone https://github.com/YOUR_USERNAME/pokepilot.git
cd pokepilot
```

### 2. 创建虚拟环境

```bash
# 使用Conda
conda create -n pokepilot-dev python=3.11
conda activate pokepilot-dev

# 或使用venv
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt

# 推荐：安装开发工具（可选）
pip install pytest flake8 black
```

### 4. 运行初始化脚本

```bash
# macOS/Linux/WSL/Git Bash
bash init.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File init.ps1
```

## 代码规范

### 命名约定

- **文件名**：使用snake_case（`pokemon_builder.py`）
- **变量/函数**：使用snake_case（`get_pokemon_data`）
- **类名**：使用PascalCase（`PokemonBuilder`）
- **常量**：使用UPPER_SNAKE_CASE（`MAX_TEAM_SIZE = 6`）

### 代码风格

- 使用4个空格缩进
- 每行最长120个字符
- 在函数和类前后使用两个空行
- 在类的方法之间使用一个空行

示例：
```python
class PokemonTeam:
    """宝可梦队伍管理器"""
    
    def __init__(self, max_size: int = 6):
        self.max_size = max_size
        self.roster = []
    
    def add_pokemon(self, pokemon: Pokemon) -> bool:
        """添加宝可梦到队伍"""
        if len(self.roster) >= self.max_size:
            return False
        self.roster.append(pokemon)
        return True
```

### 注释和文档

- 仅在**WHY**非显而易见时添加注释
- 为公开的类和函数添加docstring
- 使用有意义的变量名来增强代码可读性

### 中文支持

- 代码中的字符串可使用中文
- 注释可使用中文
- 确保文件编码为UTF-8

## 提交流程

### 1. 创建功能分支

```bash
git checkout -b feature/add-new-feature
# 或
git checkout -b fix/fix-bug-description
```

分支命名规范：
- 新功能：`feature/descriptive-name`
- Bug修复：`fix/descriptive-name`
- 文档更新：`docs/update-readme`

### 2. 提交代码

```bash
git add .
git commit -m "清晰的提交信息"
```

**提交消息规范**（遵循Conventional Commits）：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type包括：**
- `feat`：新功能
- `fix`：Bug修复
- `docs`：文档更新
- `refactor`：代码重构（不改变功能）
- `perf`：性能优化
- `test`：测试相关
- `chore`：构建、依赖等杂项

**示例：**
```
feat(ui): add dark mode toggle to settings page

Add a toggle button in the settings page to switch between light and dark themes.
User preference is saved to localStorage.

Closes #123
```

### 3. Push和创建Pull Request

```bash
git push origin feature/add-new-feature
```

然后在GitHub上创建Pull Request。

## Pull Request指南

提交PR时，请确保：

- ✅ **标题清晰**：描述你做了什么
- ✅ **描述详细**：
  - 这个PR解决了什么问题？
  - 实现方式是什么？
  - 有什么breaking changes吗？
- ✅ **代码遵循规范**：见上面的代码风格部分
- ✅ **没有冲突**：与main分支无冲突
- ✅ **测试通过**（如果有的话）

**PR模板示例：**

```markdown
## 描述
简述这个PR做了什么

## 问题类型
- [ ] Bug修复
- [ ] 新功能
- [ ] 文档更新

## 相关Issue
关闭 #123

## 测试方式
如何验证这个变更是否有效

## 截图（如果适用）
图片或视频演示

## 检查清单
- [ ] 代码遵循项目风格
- [ ] 已自测功能
- [ ] 更新了文档（如果需要）
```

## 项目结构说明

- `pokepilot/` - 主应用代码
  - `common/` - 核心数据模型
  - `detect_team/` - 队伍检测模块
  - `ui/` - Web UI
  - `data/` - 数据处理
  - `tools/` - 工具集
  - `debug_tools/` - 调试工具

- `data/` - 本地数据存储
- `screenshots/` - 测试截图
- `init.sh` / `init.ps1` - 初始化脚本

## 常见问题

**Q: 我可以修改什么？**  
A: 欢迎修改代码、文档、测试。对于大的架构变更，请先创建Issue讨论。

**Q: 如何运行项目？**  
A: 参考README.md的"使用"部分。

**Q: 我发现了安全漏洞该怎么办？**  
A: 请不要创建公开Issue。直接发送邮件至 haoanwcs@gmail.com。

## 许可证

通过贡献代码，你同意你的代码将被许可证下发布（MIT）。

## 需要帮助？

- 查看[README.md](README.md)了解项目概况
- 提交Issue提出问题
- 讨论区交流想法

感谢你的贡献！🎉
