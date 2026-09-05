# Python 装饰器与闭包

## 闭包的定义

闭包指函数引用了定义它的外层作用域中的变量，且该函数在其外层作用域之外被调用时仍然"记住"这些变量。Python 中闭包形成的条件是：内层函数引用外层函数的局部变量，且外层函数返回内层函数。闭包捕获的是变量而非值——如果内层函数只读取变量，行为符合直觉；若要修改外层变量，需要用 `nonlocal` 声明。

```python
def make_counter():
    count = 0
    def counter():
        nonlocal count
        count += 1
        return count
    return counter
```

上面 `counter` 就是闭包，`count` 是它的自由变量。没有 `nonlocal` 时对 `count` 的赋值会被解释为创建局部变量，从而抛出 `UnboundLocalError`。

## 装饰器原理

装饰器本质是一个接受函数作为参数、返回新函数的高阶函数。`@decorator` 语法等价于 `func = decorator(func)`。装饰器在**函数定义时**执行（导入模块时），而不是调用时执行，这决定了装饰器常用于注册（如 Flask 的路由注册）而不是业务逻辑。

```python
def timer(func):
    import functools, time
    @functools.wraps(func)  # 保留原函数的 __name__ 与 __doc__
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        print(f"{func.__name__} 耗时 {time.perf_counter() - start:.4f}s")
        return result
    return wrapper
```

`functools.wraps` 把原函数的元数据（`__name__`、`__doc__`、`__module__` 等）复制到包装函数上，避免调试时看到的是 `wrapper` 而不是原函数名。

## 带参数的装饰器

需要给装饰器传参时，要再包一层"装饰器工厂"：外层函数接收参数并返回真正的装饰器。使用方式从 `@timer` 变为 `@repeat(3)`，执行顺序是 `repeat(3)` 先被调用、返回的装饰器再作用于目标函数。常见的参数化装饰器包括 `@lru_cache(maxsize=128)` 这种带配置的缓存装饰器。

## 装饰器的执行顺序

多个装饰器叠加时从下往上应用：`@a` 在上、`@b` 在下等价于 `func = a(b(func))`，即最靠近函数定义的装饰器最先执行。利用这一点可以实现"鉴权在外、日志在内"的分层。

## 常见应用

- 缓存：`functools.lru_cache` 按参数缓存返回值，加速递归与重复计算
- 日志与计时：无侵入地给函数加观测
- 权限校验：Web 框架中给视图函数加登录检查
- 重试：封装指数退避的重试逻辑，如网络请求
