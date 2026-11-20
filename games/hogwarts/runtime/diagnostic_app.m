#import <Cocoa/Cocoa.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

extern char **environ;
static int noninteractive;

static void fail(NSString *message) {
    fprintf(stderr, "Hogwarts diagnostic: %s\n", message.UTF8String);
    if (noninteractive) return;
    [NSApplication sharedApplication];
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"诊断程序无法启动";
    alert.informativeText = message;
    [alert runModal];
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        noninteractive = argc == 2 && (!strcmp(argv[1], "--smoke-test") || !strcmp(argv[1], "--verify"));
        NSDictionary *config = [NSDictionary dictionaryWithContentsOfURL:
            [NSBundle.mainBundle URLForResource:@"DiagnosticConfig" withExtension:@"plist"]];
        NSString *runtime = config[@"RuntimeDirectory"];
        if (![runtime isKindOfClass:NSString.class] || !runtime.isAbsolutePath) {
            fail(@"缺少有效的诊断工作目录配置，请重新生成测试 App。");
            return 1;
        }
        NSString *host = [runtime stringByAppendingPathComponent:@"build/hogwarts-native-diagnostic"];
        NSString *modules = [runtime stringByAppendingPathComponent:@"rewritten/hogwarts"];
        NSString *romfs = [runtime stringByAppendingPathComponent:@"extracted/hogwarts/romfs/runtime-index.bin"];
        NSString *translator = [runtime stringByAppendingPathComponent:@"build/shader-service/totk_xlate"];
        NSString *cross = [runtime stringByAppendingPathComponent:@"build/spirv-cross/spirv-cross"];
        NSFileManager *fm = NSFileManager.defaultManager;
        BOOL isDir = NO;
        if (![fm isExecutableFileAtPath:host] || ![fm fileExistsAtPath:modules isDirectory:&isDir] || !isDir ||
            ![fm isReadableFileAtPath:romfs] || ![fm isExecutableFileAtPath:translator] ||
            ![fm isExecutableFileAtPath:cross]) {
            fail(@"诊断程序、游戏数据或着色器工具缺失。请保留原工作目录并重新运行打包命令。");
            return 1;
        }
        if (argc == 2 && !strcmp(argv[1], "--verify")) {
            puts("diagnostic configuration valid; GPU submission disabled on launch");
            return 0;
        }
        int smokeTest = argc == 2 && !strcmp(argv[1], "--smoke-test");
        if (argc != 1 && !smokeTest) {
            fprintf(stderr, "unsupported diagnostic launcher argument\n");
            return 2;
        }
        NSString *data = [runtime stringByAppendingPathComponent:@"hogwarts-diagnostic-app-data"];
        if (mkdir(data.fileSystemRepresentation, 0700) && errno != EEXIST) {
            fail([NSString stringWithFormat:@"无法创建隔离的诊断数据目录：%s", strerror(errno)]);
            return 1;
        }
        struct stat dataAttributes;
        if (lstat(data.fileSystemRepresentation, &dataAttributes) ||
            !S_ISDIR(dataAttributes.st_mode) || dataAttributes.st_uid != getuid()) {
            fail(@"诊断数据目录不是当前用户拥有的普通目录，拒绝使用。");
            return 1;
        }
        NSString *log = [data stringByAppendingPathComponent:@"diagnostic.log"];
        if (!smokeTest) {
            [NSApplication sharedApplication];
            [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
            [NSApp activateIgnoringOtherApps:YES];
            NSAlert *warning = [NSAlert new];
            warning.messageText = @"霍格沃茨诊断测试（不可游玩）";
            warning.informativeText = [NSString stringWithFormat:
                @"GPU 提交被强制关闭，部分绘制会跳过；不会显示有效游戏画面。诊断存档与正常存档分开。\n\n日志：%@", log];
            [warning addButtonWithTitle:@"启动诊断"];
            [warning addButtonWithTitle:@"取消"];
            if ([warning runModal] != NSAlertFirstButtonReturn) return 0;
        }
        int fd = open(log.fileSystemRepresentation, O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW, 0600);
        if (fd < 0 || dup2(fd, STDOUT_FILENO) < 0 || dup2(fd, STDERR_FILENO) < 0) {
            if (fd >= 0) close(fd);
            fail(@"无法打开诊断日志，请检查工作目录权限。");
            return 1;
        }
        if (fd > STDERR_FILENO) close(fd);
        NSMutableArray<NSString *> *remove = [NSMutableArray array];
        for (char **entry = environ; *entry; entry++) {
            const char *eq = strchr(*entry, '=');
            if (!eq) continue;
            size_t n = (size_t)(eq - *entry);
            if ((n >= 5 && !strncmp(*entry, "TOTK_", 5)) ||
                (n >= 4 && !strncmp(*entry, "OT0_", 4)) ||
                (n >= 9 && !strncmp(*entry, "HOGWARTS_", 9)) ||
                (n >= 3 && !strncmp(*entry, "DM_", 3)))
                [remove addObject:[[NSString alloc] initWithBytes:*entry length:n encoding:NSUTF8StringEncoding]];
        }
        for (NSString *key in remove) unsetenv(key.UTF8String);
        if (chdir(runtime.fileSystemRepresentation) ||
            setenv("TOTK_GPU_NOCOMMIT", "1", 1) ||
            setenv("TOTK_GPU_KEEPALIVE", "0", 1) ||
            setenv("TOTK_PROFILE_DIR", data.fileSystemRepresentation, 1) ||
            setenv("HOGWARTS_SKIP_INDIRECT_DRY_RUN", "1", 1) ||
            setenv("HOGWARTS_SKIP_UNSUPPORTED_STAGES_DRY_RUN", "1", 1)) {
            fail([NSString stringWithFormat:@"无法设置诊断环境：%s", strerror(errno)]);
            return 1;
        }
        fprintf(stderr, "\n[hogwarts-app] diagnostic launch; GPU submission disabled; output invalid\n");
        execl(host.fileSystemRepresentation, host.fileSystemRepresentation, modules.fileSystemRepresentation, "boot", NULL);
        fail([NSString stringWithFormat:@"无法启动诊断宿主：%s", strerror(errno)]);
        return 1;
    }
}
