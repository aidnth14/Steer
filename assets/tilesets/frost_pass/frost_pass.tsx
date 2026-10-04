<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" name="frost_pass" tilewidth="16" tileheight="16" tilecount="30" columns="5">
 <image source="frost_pass_sheet.png" width="80" height="96"/>
 <tile id="0"><properties><property name="name" value="dirt_corner_tl"/><property name="role" value="outer corner"/></properties></tile>
 <tile id="1"><properties><property name="name" value="dirt_edge_top"/><property name="role" value="edge"/></properties></tile>
 <tile id="2"><properties><property name="name" value="dirt_corner_tr"/><property name="role" value="outer corner"/></properties></tile>
 <tile id="5"><properties><property name="name" value="dirt_edge_left"/><property name="role" value="edge"/></properties></tile>
 <tile id="6"><properties><property name="name" value="dirt_center"/><property name="role" value="fill"/></properties></tile>
 <tile id="7"><properties><property name="name" value="dirt_edge_right"/><property name="role" value="edge"/></properties></tile>
 <tile id="10"><properties><property name="name" value="dirt_corner_bl"/><property name="role" value="outer corner"/></properties></tile>
 <tile id="11"><properties><property name="name" value="dirt_edge_bottom"/><property name="role" value="edge"/></properties></tile>
 <tile id="12"><properties><property name="name" value="dirt_corner_br"/><property name="role" value="outer corner"/></properties></tile>
 <tile id="3"><properties><property name="name" value="dirt_inner_tl"/><property name="role" value="inner corner"/></properties></tile>
 <tile id="4"><properties><property name="name" value="dirt_inner_tr"/><property name="role" value="inner corner"/></properties></tile>
 <tile id="8"><properties><property name="name" value="dirt_inner_bl"/><property name="role" value="inner corner"/></properties></tile>
 <tile id="9"><properties><property name="name" value="dirt_inner_br"/><property name="role" value="inner corner"/></properties></tile>
 <tile id="16"><properties><property name="name" value="checktile3"/><property name="role" value="finish line, top edge"/></properties></tile>
 <tile id="20"><properties><property name="name" value="checktile1"/><property name="role" value="finish line, left edge"/></properties></tile>
 <tile id="21"><properties><property name="name" value="checktile"/><property name="role" value="finish line fill"/></properties></tile>
 <tile id="22"><properties><property name="name" value="checktile2"/><property name="role" value="finish line, right edge"/></properties></tile>
 <tile id="26"><properties><property name="name" value="checktile4"/><property name="role" value="finish line, bottom edge"/></properties></tile>
 <wangsets>
  <wangset name="Frost Pass" type="corner" tile="6">
   <wangcolor name="road" color="#7e8f9a" tile="-1" probability="1"/>
   <wangcolor name="off-road" color="#f0f8ff" tile="-1" probability="1"/>
   <wangtile tileid="0" wangid="0,2,0,1,0,2,0,2"/>
   <wangtile tileid="1" wangid="0,2,0,1,0,1,0,2"/>
   <wangtile tileid="2" wangid="0,2,0,2,0,1,0,2"/>
   <wangtile tileid="5" wangid="0,1,0,1,0,2,0,2"/>
   <wangtile tileid="6" wangid="0,1,0,1,0,1,0,1"/>
   <wangtile tileid="7" wangid="0,2,0,2,0,1,0,1"/>
   <wangtile tileid="10" wangid="0,1,0,2,0,2,0,2"/>
   <wangtile tileid="11" wangid="0,1,0,2,0,2,0,1"/>
   <wangtile tileid="12" wangid="0,2,0,2,0,2,0,1"/>
   <wangtile tileid="3" wangid="0,1,0,1,0,1,0,2"/>
   <wangtile tileid="4" wangid="0,2,0,1,0,1,0,1"/>
   <wangtile tileid="8" wangid="0,1,0,1,0,2,0,1"/>
   <wangtile tileid="9" wangid="0,1,0,2,0,1,0,1"/>
  </wangset>
 </wangsets>
</tileset>
