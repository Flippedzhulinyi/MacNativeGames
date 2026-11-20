#define HOGWARTS_EXPERIMENTAL 1
#import "../games/ot0/runtime/frontend.m"

int main(void) {
 @autoreleasepool {
  [NSApplication sharedApplication];
  bootOverlay=[NSView new];
  bootStage=[NSTextField labelWithString:@""];
  bootDetail=[NSTextField labelWithString:@""];
  bootProgress=[NSProgressIndicator new];
  setenv("TOTK_GPU_NOCOMMIT","1",1);
  runtime_warm_progress(1918,1918,1711,1840,37,37);
  runtime_warm_done();
  dispatch_async(dispatch_get_main_queue(), ^{
   if (bootOverlay.hidden || !bootProgress.hidden ||
       ![bootStage.stringValue isEqualToString:@"着色器预热已结束"] ||
       ![bootDetail.stringValue containsString:@"无游戏画面"]) exit(1);
   unsetenv("TOTK_GPU_NOCOMMIT");setenv("TOTK_GPU_ALLOW_SUBMIT","1",1);
   runtime_warm_done();
   dispatch_async(dispatch_get_main_queue(), ^{
    if (![bootDetail.stringValue containsString:@"等待首个画面"]) exit(2);
    atomic_store(&presentedFrames,1);
    runtime_warm_done();
    dispatch_async(dispatch_get_main_queue(), ^{
     exit(bootOverlay.hidden ? 0 : 3);
    });
   });
  });
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),dispatch_get_main_queue(),^{exit(4);});
  [NSApp run];
 }
 return 4;
}
