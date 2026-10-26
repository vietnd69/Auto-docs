# Đề xuất cấu trúc DST docs sau kiểm chứng source

Ngày kiểm chứng: 2026-10-26. Trạng thái: đề xuất, chưa áp dụng vào doc-plan hay website.

## 1. Nguồn và giới hạn kiểm chứng

- Repository: https://github.com/vietnd69/dst-scripts
- `main` tại thời điểm kiểm tra: `b729a8f68d4b635c21279e71723b9627f24c5c38` (build 759671).
- GitHub recursive tree trả `truncated=false`: kiểm kê toàn bộ đường dẫn và kích thước blob.
- Working tree local vẫn ở `8aa91ab` (725977); không checkout/reset. Số liệu test và chi phí trước đó ở build này không phải số liệu của plan mới.
- Source mẫu đọc qua GitHub tại SHA cố định; parser hiện hành được thử trực tiếp trên nội dung đó.
- Graph service không kết nối được. Đây là kiểm kê đầy đủ cây file và kiểm chứng các mẫu cấu trúc đại diện, không phải audit ngữ nghĩa toàn bộ 4084 file.
- Dữ liệu kiểm kê và source mẫu của lượt audit nằm trong `.cache/dst-structure-audit/` (scratch, không phải cấu hình chạy).

## 2. Kiểm kê tại build 759671

| Nhóm nguồn | File Lua |
|---|---:|
| prefabs | 1618 |
| components | 831 |
| map | 447 |
| widgets | 274 |
| stategraphs | 264 |
| root | 223 |
| brains | 196 |
| screens | 136 |
| scenarios | 50 |
| behaviours | 29 |
| util | 9 |
| cameras, languages, nis, tools | 7 |
| **Tổng** | **4084** |

Trong components có 19 file `_replica.lua`. Trong map có 343 static layout, 42 room file, 10 task file, 4 taskset, 4 level và 44 module trực tiếp dưới map. Có 60 file lớn hơn 80000 byte. File lớn không đồng nghĩa cần nhiều trang văn xuôi: static layout và stategraph phải được xử lý khác nhau.

## 3. Các mẫu đã xác nhận và hệ quả

Liên kết dưới đây đều pin vào commit kiểm chứng.

| Bằng chứng source | Hệ quả đối với docs |
|---|---|
| [modutil.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/modutil.lua#L178) cài API qua `env.*`; `GetModConfigData` có wrapper khác chữ ký global | Có nhóm Modding API riêng. Lập chỉ mục API trong môi trường mod và ghi rõ modmain/modworldgenmain/frontend; không dùng nhầm helper nội bộ làm API |
| [combat_replica.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/components/combat_replica.lua#L1) dùng netvars, classified và nhánh master/client | Ghép navigation component/replica; giữ receiver `inst.components` và `inst.replica` riêng, không gộp chữ ký trùng tên |
| [netvars.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/netvars.lua#L1) ghi contract với engine và dirty event | Có networking reference; ghi ranh giới contract Lua có bằng chứng với phần native không có implementation trong repo |
| [axe.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/prefabs/axe.lua#L291) export axe, goldenaxe, moonglassaxe, fumaroleaxe qua MakeAxe | Một trang family axes, bảng khác biệt biến thể, mỗi prefab ID có anchor tra cứu. Không bắt buộc bốn trang lặp logic |
| [SGpig.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/stategraphs/SGpig.lua#L318) thêm walk/run/sleep và nhiều state qua CommonStates | State reference phải gồm state trực tiếp và state được thêm qua helper; lưu provenance của từng state và các tham số ghi đè |
| [map/rooms/cave/ruins.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/map/rooms/cave/ruins.lua#L14) đăng ký AddRoom; [map/tasks/forest.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/map/tasks/forest.lua#L7) đăng ký AddTask | Coverage theo room/task ID, không chỉ tên hàm. Có liên kết level/taskset/task/room/layout khi source chứng minh quan hệ |
| [preparedfoods.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/preparedfoods.lua#L3) chứa callback test trong bảng recipe | Đây là registry có logic, không phải dữ liệu thuần. Sinh bảng bằng code nhưng review callback và điều kiện chọn recipe |
| [scenarios/chest_abandonedboat.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/scenarios/chest_abandonedboat.lua#L21) có loot và callback count/initfn | Có scenario reference riêng, liên kết prefab/worldgen; không giản lược thành bảng loot tĩnh |
| [brains/pigbrain.lua](https://github.com/vietnd69/dst-scripts/blob/b729a8f68d4b635c21279e71723b9627f24c5c38/brains/pigbrain.lua#L1) dùng nhiều behaviour module | Navigation AI gồm brains và behaviours; mô tả điều kiện, thứ tự ưu tiên và liên kết stategraph thay vì chỉ liệt kê method |

## 4. Cấu trúc website đề xuất

```text
docs/
  index.md
  getting-started/                 # đọc docs, mod entrypoints, runtime contexts
  guides/                          # tác vụ thực tế; triển khai chọn lọc sau reference
  systems/                         # luồng liên module: boats, combat, inventory...
  reference/
    modding/                       # hooks, recipes, RPC, worldgen hooks
    runtime/                       # Class, EntityScript, scheduler, bootstrap
    networking/                    # netvars, RPC, shard, classified contracts
    actions/                       # actions, componentactions, bufferedaction
    crafting/                      # recipe/cooking APIs; link sang catalog dữ liệu
    components/
      boatdrag.md
      combat/
        index.md
        targeting.md
        damage.md
        replica.md
    prefabs/
      tools/axes.md                 # family thực tế có factory chung
      ...
    ai/
      brains/
      behaviours/
      stategraphs/
        common/
        sgwilson/
          index.md
          locomotion.md
          combat.md
          interaction.md
    ui/
      widgets/
      screens/
    worldgen/
      index.md
      levels/
      tasksets/
      tasks/
      rooms/
      layout-api.md
    scenarios/
    utilities/
    debugging/
    presentation/                  # camera/audio/cinematic khi có API hữu ích
  data/
    tuning/
    strings/
    recipes/                       # dữ liệu chọn lọc + callback có ý nghĩa
    skins/
    layouts/                       # schema + catalog sinh tự động
    catalogs/                      # các registry còn lại, phân theo chức năng
  changes/
```

Các tên nhóm chức năng là đề xuất, chưa phải ownership map hoàn chỉnh. Không tạo trang rỗng chỉ để đủ cây. Nhóm data/skins phải thu thập nguồn theo cấu trúc nội dung, không chỉ thư mục: ví dụ `screens/redux/scrapbookdata.lua` là ứng viên catalog dù nằm trong screens.

Reference là nơi mô tả chính của API. Systems mô tả cách các API phối hợp. Guides chỉ trình bày một tác vụ có precondition và cleanup rõ ràng rồi link về reference. Search index cho phép tra source path, symbol, prefab ID, state/room/task/recipe ID ngay cả khi nhiều ID ở chung một trang.

## 5. Quy tắc ownership, gộp/tách và coverage

1. Component nhỏ giữ trang riêng. Component có replica có thể chung một trang với section rõ ràng nếu ngắn; khi tách, đặt replica cạnh component trong navigation. Không làm mất danh tính receiver server/client.
2. Component lớn tách theo trách nhiệm được chứng minh bằng callers, field/event dùng chung. Không dùng `methods-1`, `functions-2` làm tên trang người đọc.
3. Prefab family chỉ gộp sau khi xác minh factory/logic chung, lifecycle và khác biệt. Cùng thư mục hoặc giống tên chưa đủ điều kiện gộp.
4. Stategraph nhỏ giữ một trang; lớn tách theo nhóm hành vi. State, event handler và action mapping liên quan được đọc cùng nhau. CommonStates có trang mô tả chính; graph sử dụng nó có bảng state hiệu lực và ghi phần override.
5. Worldgen chia theo registry và phạm vi surface/caves khi nguồn có phân biệt. Static layouts có schema, catalog có link từng ID, samples; không cần 343 bài văn dài.
6. Dữ liệu thuần sinh bằng code. Bảng có callback/nhánh/runtime mutation dùng chế độ kết hợp. Giá trị không xác định được bằng phân tích tĩnh phải giữ biểu thức hoặc đánh dấu chưa giải quyết; không tự chạy tùy ý Lua để đoán.
7. Public API, registry entry, property, callback contract, injected state và native contract là các loại đối tượng docs khác nhau. Mỗi đối tượng có một mô tả chính; helper private chỉ xuất hiện khi cần giải thích hành vi hoặc là điểm mở rộng có bằng chứng.
8. Coverage API đo theo đối tượng; coverage data đo theo schema/catalog và số entry được lập chỉ mục. Mọi file đều phải có disposition rõ: reference, catalog, supporting-source hoặc excluded-with-reason. Không coi file không có symbol parser là đã được tài liệu hóa.

Thiết kế 2026-10-25 đã cho phép bỏ URL cũ; đề xuất này không yêu cầu redirect. Sau khi chốt plan mới, page ID và anchor phải ổn định qua update.

## 6. Tách trang khỏi đơn vị xử lý

- Trang được chia để người đọc hiểu một trách nhiệm; không phụ thuộc kích thước context của một request.
- Một work unit khởi đầu khoảng 5–10 API đơn giản, hoặc một cụm nhỏ có quan hệ chặt; symbol dài có thể cần một unit riêng. Đây là tham số pilot, không phải ngưỡng chất lượng đã đo.
- Budget gồm source, dependencies, output dự kiến, số tool call và repair; không chỉ 12000 token nguồn.
- Writer/reviewer xử lý từng unit, checkpoint theo unit. Sau khi ghép, review toàn trang kiểm tra ví dụ, precondition, lifecycle và tính nhất quán liên section.
- Trang PASS phải có cả coverage unit và review tổng hợp, không chỉ không còn finding mở.

## 7. Những thay đổi cần có trước khi re-plan

Kiểm thử parser hiện tại trên source tại b729a8f cho kết quả:

| Source | Kết quả hiện tại | Khoảng trống |
|---|---|---|
| modutil.lua | 12 public symbols; không có AddPrefabPostInit, AddComponentPostInit, AddRecipe2 | API env.* trong InsertPostInitFunctions bị bỏ sót |
| prefabs/axe.lua | Public list là các helper; không có symbol kind prefab | Chưa resolve tên prefab được trả qua factory |
| SGpig.lua | 11 state khai báo trực tiếp được parse | Chưa có state hiệu lực được CommonStates thêm |
| map/tasks/forest.lua | Public list rỗng | Không lập chỉ mục AddTask registry |
| map/rooms/cave/ruins.lua | Public list chỉ bgwilds, bgsacred | Thiếu AddRoom entries |
| preparedfoods.lua | Có table trong parser nhưng public list rỗng; is_data=false | Chưa mô hình hóa recipe registry có callback |

Các kết quả này không chứng minh writer không thể đọc source, nhưng chứng minh deterministic checklist chưa đủ để bảo đảm coverage. Cần extractor cho các mẫu trên và explicit unresolved records trước khi tuyên bố 100%.

Plan nên tách các trường `page_type`, `domain`, `owns`, `references`, `depends_on`, `runtime_scope`, `work_units`, `generation_mode`. Đây là schema đề xuất, chưa được code hỗ trợ. Dùng ID định danh theo module/receiver/registry; ví dụ API trong env mod phải khác helper global cùng tên.

`depends_on` cần theo dõi symbol/schema được dùng làm bằng chứng, không chỉ require trực tiếp. Ví dụ docs boatdrag phụ thuộc consumer boatphysics; đổi logic consumer phải đưa trang vào diện review. Cần giới hạn dependency tới claim/section liên quan để tránh chạy lại cả codebase.

## 8. Lộ trình và đầu ra để duyệt

1. Chốt source SHA 759671 cho plan mới; không dùng lại plan/index/cost của 725977 như cùng một tập dữ liệu.
2. Bổ sung extractor + regression fixtures cho env hooks, factory prefab, registry, injected states và data callback.
3. Sinh inventory objects và disposition mọi file. Báo unresolved thay vì bỏ qua.
4. Sinh candidate plan với ownership, semantic grouping và work units. Chạy coverage, dangling links, collisions, budget và dependency checks.
5. Pilot khoảng 24 trang, có cả API nhỏ/lớn, replica, factory prefab, SGpig/SGwilson, UI, worldgen, pure data và mixed data. Có review thủ công đối chứng trên ví dụ và preconditions.
6. Đo cost trên trang được duyệt đạt, false-positive/false-negative của reviewer, retry và cache; rồi mới dự trù full run.
7. Generate reference + catalogs trước; thêm systems/guides theo nhu cầu và các luồng được kiểm chứng. Chưa bật publish hàng loạt.

Chưa đề xuất số trang đích: 4084 file không đồng nghĩa 4084 trang, nhưng giảm số trang không tự đảm bảo giảm chi phí. Số trang chỉ chốt sau ownership map và pilot.
