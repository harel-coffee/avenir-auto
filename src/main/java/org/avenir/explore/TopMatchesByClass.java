/*
 * avenir: Predictive analytic based on Hadoop Map Reduce
 * Author: Pranab Ghosh
 * 
 * Licensed under the Apache License, Version 2.0 (the "License"); you
 * may not use this file except in compliance with the License. You may
 * obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0 
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

package org.avenir.explore;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.NullWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;
import org.chombo.util.SecondarySort;
import org.chombo.util.Tuple;
import org.chombo.util.Utility;

/**
 * Top match map reduce based on distance with neighbors and partitioned by 
 * class attribute
 * @author pranab
 *
 */
public class TopMatchesByClass extends Configured implements Tool {

	@Override
	public int run(String[] args) throws Exception {
        Job job = new Job(getConf());
        String jobName = "Top n matches by class attribute  MR";
        job.setJobName(jobName);
        
        job.setJarByClass(TopMatchesByClass.class);
        
        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        
        job.setMapperClass(TopMatchesByClass.TopMatchesMapper.class);
        job.setReducerClass(TopMatchesByClass.TopMatchesReducer.class);
        job.setCombinerClass(TopMatchesByClass.TopMatchesCombiner.class);
        
        job.setMapOutputKeyClass(Tuple.class);
        job.setMapOutputValueClass(Tuple.class);

        job.setOutputKeyClass(NullWritable.class);
        job.setOutputValueClass(Text.class);
        
        job.setGroupingComparatorClass(SecondarySort.TuplePairGroupComprator.class);
        job.setPartitionerClass(SecondarySort.TuplePairPartitioner.class);

        Utility.setConfiguration(job.getConfiguration());
        int numReducer = job.getConfiguration().getInt("tmc.num.reducer", -1);
        numReducer = -1 == numReducer ? job.getConfiguration().getInt("num.reducer", 1) : numReducer;
        job.setNumReduceTasks(numReducer);
        
        int status =  job.waitForCompletion(true) ? 0 : 1;
        return status;
	}
	
	/**
	 * @author pranab
	 *
	 */
	public static class TopMatchesMapper extends Mapper<LongWritable, Text, Tuple, Tuple> {
		private String srcEntityId;
		private String trgEntityId;
		private int rank;
		private Tuple outKey = new Tuple();
		private Tuple outVal = new Tuple();
        private String fieldDelimRegex;
        private String fieldDelim;
        private int recLength = -1;
        private int srcRecBeg;
        private int srcRecEnd;
        private int trgRecBeg;
        private int trgRecEnd;
        private int classAttrOrd;
        private String srcClassAttr;
        private String trgClassAttr;

        /* (non-Javadoc)
         * @see org.apache.hadoop.mapreduce.Mapper#setup(org.apache.hadoop.mapreduce.Mapper.Context)
         */
        protected void setup(Context context) throws IOException, InterruptedException {
			Configuration conf = context.getConfiguration();
           	fieldDelim = conf.get("field.delim", ",");
            fieldDelimRegex = conf.get("field.delim.regex", ",");
        	classAttrOrd = Utility.assertIntConfigParam(conf, "tmc.class.attr.ord", 
        			"missing class attribute ordinal");
        }    

        /* (non-Javadoc)
         * @see org.apache.hadoop.mapreduce.Mapper#map(KEYIN, VALUEIN, org.apache.hadoop.mapreduce.Mapper.Context)
         */
        @Override
        protected void map(LongWritable key, Text value, Context context)
            throws IOException, InterruptedException {
            String[] items  =  value.toString().split(fieldDelimRegex);
            
            srcEntityId = items[0];
            trgEntityId = items[1];
            rank = Integer.parseInt(items[items.length - 1]);
            
            outKey.initialize();
            outVal.initialize();
            
        	//include source and taraget record
        	if (recLength == -1) {
        		recLength = (items.length - 3) / 2;
        		srcRecBeg = 2;
        		srcRecEnd =  trgRecBeg = 2 + recLength;
        		trgRecEnd = trgRecBeg + recLength;
        	}
        	srcClassAttr = items[srcRecBeg + classAttrOrd];
        	trgClassAttr = items[trgRecBeg + classAttrOrd];
        	
        	outKey.add(srcEntityId, srcClassAttr, trgClassAttr, rank);
        	outVal.add(trgEntityId, rank);            	
 			context.write(outKey, outVal);
        }
	}

    /**
     * @author pranab
     *
     */
    public static class TopMatchesCombiner extends Reducer<Tuple, Text, Tuple, Tuple> {
    	private boolean nearestByCount;
    	private int topMatchCount;
    	private int topMatchDistance;
		private int count;
		private int distance;
    
        /* (non-Javadoc)
         * @see org.apache.hadoop.mapreduce.Reducer#setup(org.apache.hadoop.mapreduce.Reducer.Context)
         */
        protected void setup(Context context) throws IOException, InterruptedException {
			Configuration conf = context.getConfiguration();
        	nearestByCount = conf.getBoolean("tmc.nearest.by.count", true);
        	if (nearestByCount) {
        		topMatchCount = conf.getInt("tmc.match.count", 10);
        	} else {
        		topMatchDistance = conf.getInt("tmc.match.distance", 200);
        	}
       }
        
       	/* (non-Javadoc)
    	 * @see org.apache.hadoop.mapreduce.Reducer#reduce(KEYIN, java.lang.Iterable, org.apache.hadoop.mapreduce.Reducer.Context)
    	 */
    	protected void reduce(Tuple key, Iterable<Tuple> values, Context context)
        	throws IOException, InterruptedException {
    		count = 0;
        	for (Tuple value : values){
        		//count based neighbor
				if (nearestByCount) {
					context.write(key, value);
	        		if (++count == topMatchCount){
	        			break;
	        		}
				} else {
					//distance based neighbor
					distance = value.getInt(1);
					if (distance  <=  topMatchDistance ) {
						context.write(key, value);
					} else {
						break;
					}
				}
        	}
    	}
    }
    
    /**
     * @author pranab
     *
     */
    public static class TopMatchesReducer extends Reducer<Tuple, Tuple, NullWritable, Text> {
    	private boolean nearestByCount;
    	private boolean nearestByDistance;
    	private int topMatchCount;
    	private int topMatchDistance;
		private String srcEntityId;
		private int count;
		private int distance;
		private Text outVal = new Text();
        private String fieldDelim;
        private boolean compactOutput;
        private List<String> targetEntityList = new ArrayList<String>();
    	private String srcEntityClassAttr;
       	private String trgEntityClassAttr;
		private StringBuilder stBld = new  StringBuilder();
           	
        /* (non-Javadoc)
         * @see org.apache.hadoop.mapreduce.Reducer#setup(org.apache.hadoop.mapreduce.Reducer.Context)
         */
        protected void setup(Context context) throws IOException, InterruptedException {
			Configuration conf = context.getConfiguration();
           	fieldDelim = conf.get("field.delim", ",");
        	nearestByCount = conf.getBoolean("tmc.nearest.by.count", true);
        	nearestByDistance = conf.getBoolean("tmc.nearest.by.distance", false);
        	if (nearestByCount) {
        		topMatchCount = conf.getInt("tmc.top.match.count", 10);
        	} else {
        		topMatchDistance = conf.getInt("tmc.top.match.distance", 200);
        	}
        	compactOutput =  conf.getBoolean("tmc.compact.output", false);     
        }
    	
    	/* (non-Javadoc)
    	 * @see org.apache.hadoop.mapreduce.Reducer#reduce(KEYIN, java.lang.Iterable, org.apache.hadoop.mapreduce.Reducer.Context)
    	 */
    	protected void reduce(Tuple key, Iterable<Tuple> values, Context context)
        	throws IOException, InterruptedException {
    		srcEntityId  = key.getString(0);
    		srcEntityClassAttr = key.getString(1);
    		trgEntityClassAttr = key.getString(2);
    		
    		count = 0;
    		boolean doEmitNeighbor = false;
    		targetEntityList.clear();
        	for (Tuple value : values){
        		doEmitNeighbor = false;
        		
        		//count based neighbor
				if (nearestByCount) {
					doEmitNeighbor = true;
	        		if (++count >= topMatchCount){
	        			doEmitNeighbor = false;
	        		}
				} 
				
				//distance based neighbors
				if (nearestByDistance) {
					//distance based neighbor
					distance = value.getInt(1);
					if (distance  <=  topMatchDistance ) {
						if (!nearestByCount) {
							doEmitNeighbor = true;
						}
					} else {
						doEmitNeighbor = false;
					}
				}
				
				if (doEmitNeighbor) {
					//along with neighbors
					if (compactOutput) {
						//contains id,record,rank - strip out entity ID and rank
						targetEntityList.add(value.getString(0));
					} else {
						stBld.delete(0, stBld.length());
						stBld.append(srcEntityId).append(fieldDelim).append(srcEntityClassAttr).
							append(fieldDelim).append(trgEntityClassAttr).append(fieldDelim).append(value.getString(0));
						outVal.set(stBld.toString());
						context.write(NullWritable.get(), outVal);
					}
				} 
        	}
        	
        	//emit in compact format
        	if (compactOutput) {
        		int numNeighbor = targetEntityList.size();
        		if (numNeighbor > 0) {
 					stBld.delete(0, stBld.length());
					stBld.append(srcEntityId).append(fieldDelim).append(srcEntityClassAttr).
						append(fieldDelim).append(trgEntityClassAttr);
					for (String targetEntity : targetEntityList) {
						stBld.append(fieldDelim).append(targetEntity);
					}
					outVal.set(stBld.toString());
					context.write(NullWritable.get(), outVal);
        		}
        		
        	}
    	}
    }
	
	/**
	 * @param args
	 * @throws Exception
	 */
	public static void main(String[] args) throws Exception {
        int exitCode = ToolRunner.run(new TopMatchesByClass(), args);
        System.exit(exitCode);
	}
}