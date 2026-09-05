# Python 生成器与迭代器

## 迭代器协议

Python 中任何实现了 `__iter__` 和 `__next__` 方法的对象都是迭代器。`__iter__` 返回迭代器自身，`__next__` 每次调用返回下一个元素；当元素耗尽时抛出 `StopIteration` 异常，`for` 循环会自动捕获它并结束遍历。判断一个对象是否可迭代，可以用 `collections.abc.Iterable` 配合 `isinstance`。

```python
class Countdown:
    def __init__(self, n):
        self.n = n
    def __iter__(self):
        return self
    def __next__(self):
        if self.n <= 0:
            raise StopIteration
        self.n -= 1
        return self.n
```

## 生成器与 yield

生成器是编写迭代器最简洁的方式：函数体中出现 `yield` 关键字，调用该函数不会执行函数体，而是返回一个生成器对象。每次 `next()` 调用会让函数执行到下一个 `yield` 处暂停并返回值，函数状态（局部变量、执行位置）被完整保留，下次继续从暂停点恢复执行。这种"可暂停的函数"模型是 Python 协程的基础。

生成器是惰性求值的：元素在需要时才被计算，因此可以用有限内存表示无限序列，比如生成全体斐波那契数。相比之下，`[x for x in range(10**8)]` 这种列表推导会一次性占用巨大内存，而生成器表达式 `(x for x in range(10**8))` 几乎不占内存。

## yield from 与 send

`yield from` 可以把一个生成器的产出委托给另一个生成器，简化嵌套遍历代码；它同时转发 `send()` 和 `throw()` 调用，是构建"生成器管道"的关键语法。生成器的 `send(value)` 方法可以给暂停中的 `yield` 表达式注入值，实现双向通信；`close()` 在暂停点抛出 `GeneratorExit` 终止生成器。

## 常见陷阱

1. 生成器只能遍历一次：迭代完后再次遍历得不到任何元素，需要重新创建生成器对象。
2. `next()` 比 `for` 多抛一次 `StopIteration`，注意捕获。
3. 生成器函数不会在创建时执行——如果此时外部状态已经改变，首次迭代时可能拿到意想不到的值。

## 性能对比

处理大文件时逐行生成器读入的内存占用与文件大小无关，而 `readlines()` 会把全部行读进内存。典型基准：1GB 日志逐行处理，生成器方案峰值内存约 8MB，列表方案超过 1GB。
