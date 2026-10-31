#import <Cocoa/Cocoa.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>

static void fail(NSString *message) {
    NSAlert *alert = [NSAlert new];
    alert.messageText = @"Super Mario Odyssey could not start";
    alert.informativeText = message;
    [alert runModal];
}

static BOOL make_dir(NSString *path) {
    return [NSFileManager.defaultManager createDirectoryAtPath:path
                                   withIntermediateDirectories:YES
                                                    attributes:nil
                                                         error:nil];
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    @autoreleasepool {
        NSString *work = NSBundle.mainBundle.infoDictionary[@"OdysseyWorkFolder"];
        const char *override = getenv("ODYSSEY_WORK");
        if (override && *override) work = @(override);
        if (!work.length) {
            fail(@"No Odyssey work folder is configured.");
            return 1;
        }
        NSString *binary = [work stringByAppendingPathComponent:@"build/odyssey-native"];
        if (![NSFileManager.defaultManager isExecutableFileAtPath:binary]) {
            fail([NSString stringWithFormat:@"The Odyssey runtime was not found in %@.", work]);
            return 1;
        }

        NSString *home = NSHomeDirectory();
        NSString *data = [home stringByAppendingPathComponent:@"Library/Application Support/MacNativeGames/Odyssey"];
        NSString *logs = [home stringByAppendingPathComponent:@"Library/Logs/MacNativeGames"];
        const char *profileOverride = getenv("ODYSSEY_PROFILE_DIR");
        NSString *profile = profileOverride && *profileOverride ? @(profileOverride) : [data stringByAppendingPathComponent:@"profile"];
        const char *slotOverride = getenv("ODYSSEY_SLOT_DIR");
        NSString *slot = slotOverride && *slotOverride ? @(slotOverride) : [data stringByAppendingPathComponent:@"game-slot"];
        if (!make_dir(profile) || !make_dir(slot) || !make_dir(logs)) {
            fail([NSString stringWithFormat:@"Could not create the game data folders under %@.", data]);
            return 1;
        }
        if (chdir(work.fileSystemRepresentation)) {
            fail([NSString stringWithFormat:@"Could not open the work folder %@: %s", work, strerror(errno)]);
            return 1;
        }

        setenv("TOTK_PROFILE_DIR", profile.fileSystemRepresentation, 1);
        setenv("TOTK_GAME_SLOT_DIR", slot.fileSystemRepresentation, 1);
        setenv("TOTK_ROMFS_PROOF_DIR", data.fileSystemRepresentation, 1);
        setenv("TOTK_GPU_ALLOW_SUBMIT", "1", 1);
        setenv("DM_PRESENT_LINK_FALLBACK", "1", 1);
        setenv("TOTK_SLOT_OWNER", "user", 1);
        setenv("TOTK_SLOT_PURPOSE", "player", 1);
        unsetenv("TOTK_HEADLESS");

        NSString *input = [data stringByAppendingPathComponent:@"input.txt"];
        if (![@"" writeToFile:input atomically:YES encoding:NSUTF8StringEncoding error:nil]) {
            fail([NSString stringWithFormat:@"Could not initialize the input queue %@.", input]);
            return 1;
        }
        setenv("TOTK_INPUT_FILE", input.fileSystemRepresentation, 1);

        NSString *log = [logs stringByAppendingPathComponent:@"odyssey.log"];
        NSString *previous = [logs stringByAppendingPathComponent:@"odyssey.previous.log"];
        [NSFileManager.defaultManager removeItemAtPath:previous error:nil];
        [NSFileManager.defaultManager moveItemAtPath:log toPath:previous error:nil];
        FILE *stream = fopen(log.fileSystemRepresentation, "w");
        if (stream) {
            dup2(fileno(stream), STDOUT_FILENO);
            dup2(fileno(stream), STDERR_FILENO);
            fclose(stream);
        }
        fprintf(stderr, "[launcher] Odyssey work folder: %s\n", work.fileSystemRepresentation);
        char *const args[] = {(char *)binary.fileSystemRepresentation, "rewritten/v141", "boot", NULL};
        execv(args[0], args);
        fprintf(stderr, "[launcher] execv failed: %s\n", strerror(errno));
        fail([NSString stringWithFormat:@"Could not start the runtime. See %@.", log]);
        return 1;
    }
}