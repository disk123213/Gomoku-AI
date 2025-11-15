cmake_minimum_required(VERSION 3.15)
project(gobang_core LANGUAGES CXX)

# C++标准（兼容C++17）
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 跨平台编译选项
if (MSVC)
    # Windows：Visual Studio编译
    add_compile_options(/W4 /O2 /EHsc)
    set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
else()
    # Linux/macOS：GCC/Clang编译
    add_compile_options(-Wall -O3 -fPIC)
endif()

# 源文件
set(SOURCE_FILES
    core/gobang_core.cpp
    core/gobang_core.h
)

# 生成动态库
add_library(gobang_core SHARED ${SOURCE_FILES})

# 安装路径（输出到cpp/build目录）
set_target_properties(gobang_core PROPERTIES
    ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

# 头文件安装（供CPython调用）
install(FILES core/gobang_core.h DESTINATION include)
install(TARGETS gobang_core LIBRARY DESTINATION lib RUNTIME DESTINATION bin ARCHIVE DESTINATION lib)